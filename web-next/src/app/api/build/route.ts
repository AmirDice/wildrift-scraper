import { spawn } from "node:child_process";
import path from "node:path";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { SESSION_COOKIE, readSession } from "@/lib/session";
import { ACCESS_COOKIE, readAccessCookie } from "@/lib/access";
import { ANON_DAILY_BUILDS, clientIp, consumeQuota, peekQuota, refundQuota } from "@/lib/quota";
import { buildCacheKey, readCachedBuild, writeCachedBuild } from "@/lib/build-cache";
import { checkAbuseGuards } from "@/lib/build-guards";
import { trackEvent } from "@/lib/stats";

/**
 * Live build advisor. POST { champion, role, enemies[], allies[], playstyle, mode }
 * -> the validated JSON build from the Python advisor.
 *
 * This route owns everything that needs the request context -- Google session,
 * daily quota, KV cache, event tracking -- and delegates only the generation
 * itself. The whole data pipeline (items, runes, matchups, champion profiles and
 * build rules) lives in Python and stays there: re-implementing it in TypeScript
 * would mean maintaining two copies of the same rules, which this project has
 * already had drift apart more than once.
 *
 * In production the advisor is a Vercel Python function (api/advisor.py, 300s
 * ceiling). Locally there is no such function, so we spawn the module directly
 * and skip the network hop.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";
// The advisor can take a minute, and longer when a repair round fires. Vercel
// allows 300s on every plan; this must be at least as long as TIMEOUT_MS below.
export const maxDuration = 300;

// repo root = parent of the web-next dir this app runs from
const REPO_ROOT = path.resolve(process.cwd(), "..");
const PY = process.env.PYTHON_BIN || "python";
// Thinking-mode generations now include the mandatory item audit and complete
// LLM build evaluation, so allow the same four-minute ceiling as the advisor.
const TIMEOUT_MS = 240_000;
// Set on Vercel; absent locally, which is what selects the subprocess path.
const ADVISOR_URL = process.env.ADVISOR_URL
  || (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}/api/advisor` : "");
const ADVISOR_SECRET = process.env.ADVISOR_SECRET || "";

// The daily cap lives in src/lib/quota.ts: 10 generations per IP per day, plus
// another 10 for anyone signed in with Google. It exists because every
// generation costs a real DeepSeek call (~$0.003), so an unattended script
// could otherwise run up the bill.

type Body = {
  champion?: string;
  role?: string;
  enemies?: string[];
  allies?: string[];
  playstyle?: string;
  objective?: string;
  gamePhase?: string;
  damagePath?: string;
  championForm?: string;
  aheadEnemy?: string;
  mode?: string;
  riskTolerance?: string;
  lockedItems?: string[];
  lockedRunes?: string[];
};

type AdvisorResult =
  | { ok: true; data: unknown }
  | {
      ok: false;
      error: string;
      /** True only when the local advisor was confirmed never to have started. */
      quotaRefundable?: boolean;
    };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Production path: the advisor as a Vercel Python function, over HTTP. */
async function callAdvisorFunction(b: Body): Promise<AdvisorResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(ADVISOR_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(ADVISOR_SECRET ? { "x-advisor-secret": ADVISOR_SECRET } : {}),
      },
      body: JSON.stringify(b),
      signal: controller.signal,
    });
    const text = await res.text();
    let data: unknown;
    try {
      data = JSON.parse(text);
    } catch {
      return { ok: false, error: `unparseable advisor response: ${text.slice(0, 300)}` };
    }
    if (!res.ok) {
      const message = (data as { error?: string })?.error ?? `advisor returned ${res.status}`;
      return { ok: false, error: message };
    }
    return { ok: true, data };
  } catch (err) {
    const aborted = err instanceof Error && err.name === "AbortError";
    return { ok: false, error: aborted ? "advisor timed out" : String(err) };
  } finally {
    clearTimeout(timer);
  }
}

/** Local path: no Python function exists on a dev machine, so run the module. */
function spawnAdvisor(b: Body): Promise<AdvisorResult> {
  return new Promise((resolve) => {
    const args = [
      "-m",
      "web.build_advisor",
      "--champion",
      b.champion ?? "",
      "--role",
      b.role ?? "",
      "--enemies",
      (b.enemies ?? []).join(","),
      "--allies",
      (b.allies ?? []).join(","),
      "--playstyle",
      b.playstyle ?? "standard",
      "--objective",
      b.objective ?? "balanced",
      "--game-phase",
      b.gamePhase ?? "balanced",
      "--damage-path",
      b.damagePath ?? "standard",
      "--champion-form",
      b.championForm ?? "",
      "--ahead-enemy",
      b.aheadEnemy ?? "",
      "--mode",
      b.mode === "counter" ? "counter" : "studio",
      "--risk-tolerance",
      b.riskTolerance ?? "medium",
      "--locked-items",
      (b.lockedItems ?? []).join(","),
      "--locked-runes",
      (b.lockedRunes ?? []).join(","),
    ];
    let out = "";
    let err = "";
    let started = false;
    let settled = false;

    let proc: ReturnType<typeof spawn>;
    try {
      proc = spawn(PY, args, {
        cwd: REPO_ROOT,
        env: { ...process.env, PYTHONUTF8: "1" },
      });
    } catch (error) {
      resolve({
        ok: false,
        error: `advisor process could not start: ${errorMessage(error)}`,
        quotaRefundable: true,
      });
      return;
    }

    const timer = setTimeout(() => {
      finish({ ok: false, error: "advisor timed out" });
      try {
        proc.kill();
      } catch {
        // The timeout response is already settled; close/error may follow.
      }
    }, TIMEOUT_MS);
    const finish = (result: AdvisorResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };

    proc.once("spawn", () => {
      started = true;
    });
    proc.once("error", (error) => {
      finish({
        ok: false,
        error: `advisor process error: ${errorMessage(error)}`,
        quotaRefundable: !started,
      });
    });

    proc.stdout?.on("data", (d) => (out += d));
    proc.stderr?.on("data", (d) => (err += d));
    proc.on("close", (code) => {
      if (code !== 0) {
        finish({ ok: false, error: err.trim() || `advisor exited ${code}` });
        return;
      }
      try {
        finish({ ok: true, data: JSON.parse(out) });
      } catch {
        finish({ ok: false, error: `unparseable advisor output: ${out.slice(0, 300)}` });
      }
    });
  });
}

/** HTTP where an advisor function exists, subprocess where one does not. */
function runAdvisor(b: Body): Promise<AdvisorResult> {
  return ADVISOR_URL ? callAdvisorFunction(b) : spawnAdvisor(b);
}

async function handlePost(request: Request) {
  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (!body.champion || typeof body.champion !== "string") {
    return NextResponse.json({ error: "champion is required" }, { status: 400 });
  }
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const access = readAccessCookie(store.get(ACCESS_COOKIE)?.value);
  const unlimited = access?.unlimited ?? false;

  // guard the shell-out: only plausible names/values reach argv
  const clean = (s: unknown) =>
    typeof s === "string" ? s.replace(/[^A-Za-z0-9 .'&-]/g, "").slice(0, 40) : "";
  const cleanList = (a: unknown) =>
    Array.isArray(a) ? a.map(clean).filter(Boolean).slice(0, 5) : [];

  const mode = clean(body.mode) === "counter" ? "counter" : "studio";
  const champion = clean(body.champion);
  const unique = (values: string[]) => [...new Set(values)];
  const enemies = unique(cleanList(body.enemies)).filter((name) => name !== champion);
  const allies = unique(cleanList(body.allies))
    .filter((name) => name !== champion && !enemies.includes(name))
    .slice(0, 4);
  if (mode === "counter" && enemies.length === 0) {
    return NextResponse.json(
      { error: "at least one enemy is required for a counter build" },
      { status: 400 },
    );
  }

  const advisorRequest = {
    champion,
    role: clean(body.role),
    enemies,
    allies,
    playstyle: clean(body.playstyle) || "standard",
    objective: clean(body.objective) || "balanced",
    gamePhase: clean(body.gamePhase) || "balanced",
    damagePath: clean(body.damagePath) || "standard",
    championForm: clean(body.championForm),
    aheadEnemy: clean(body.aheadEnemy),
    mode,
    riskTolerance: clean(body.riskTolerance) || "medium",
    // Slugs and rune names the player pinned; the advisor caps and resolves
    // them, so passing a few extra or unknown ones is harmless.
    lockedItems: cleanList(body.lockedItems),
    lockedRunes: cleanList(body.lockedRunes),
  };

  // Cache first, and before the quota is touched. Somebody else already paid
  // for this exact build on this patch, so it returns instantly and costs the
  // player nothing: charging a generation for a lookup would be charging for
  // work we did not do.
  const cacheKey = buildCacheKey(advisorRequest);
  const cached = await readCachedBuild(cacheKey);
  if (cached) {
    const quota = await peekQuota(user, clientIp(request), unlimited);
    return NextResponse.json(
      { ...cached, quota, cached: true },
      { headers: { "X-RateLimit-Remaining": String(quota.remaining), "X-Build-Cache": "hit" } },
    );
  }

  // Abuse guards run AFTER the cache lookup (a hit costs us nothing, so it
  // should not be rate limited) and BEFORE the quota is spent. They cover what
  // a daily counter cannot: bursts, concurrent runs, and rotating identities.
  const clientKey = user?.sub ? `u:${user.sub}` : `ip:${clientIp(request)}`;
  const { verdict, release } = await checkAbuseGuards(clientKey);
  if (!verdict.ok) {
    return NextResponse.json(
      { error: verdict.reason },
      { status: 429, headers: { "Retry-After": String(verdict.retryAfter) } },
    );
  }

  const ip = clientIp(request);
  try {
    const { ok, quota } = await consumeQuota(user, ip, unlimited);
    if (!ok) {
      const hours = Math.max(1, Math.ceil((quota.resetAt - Date.now()) / 3_600_000));
      return NextResponse.json(
        {
          error: quota.canUnlockBySigningIn
            ? `That is your ${ANON_DAILY_BUILDS} free builds for today. Sign in with Google for ${quota.limit} more, or come back in ~${hours}h.`
            : `Daily build limit reached (${quota.limit}/day). Resets in ~${hours}h.`,
          quota,
        },
        { status: 429, headers: { "X-RateLimit-Remaining": "0" } },
      );
    }

    const res = await runAdvisor(advisorRequest);
    if (!res.ok) {
      const responseQuota = res.quotaRefundable
        ? await refundQuota(user, ip, unlimited)
        : quota;
      return NextResponse.json(
        {
          error: res.quotaRefundable
            ? `${res.error}. Your generation was restored.`
            : res.error,
          quota: responseQuota,
          quotaRefunded: Boolean(res.quotaRefundable),
        },
        {
          status: res.quotaRefundable ? 503 : 502,
          headers: { "X-RateLimit-Remaining": String(responseQuota.remaining) },
        },
      );
    }

    if (!res.data || typeof res.data !== "object" || Array.isArray(res.data)) {
      return NextResponse.json(
        { error: "advisor returned an invalid build", quota },
        { status: 502, headers: { "X-RateLimit-Remaining": String(quota.remaining) } },
      );
    }

    const data = res.data as Record<string, unknown>;
    // Only cache a build the validator was happy with: a flagged one should get
    // another attempt rather than being served to everyone for the rest of the patch.
    const flagged = Array.isArray(data.validationErrors) && data.validationErrors.length > 0;
    if (!flagged) void writeCachedBuild(cacheKey, data);

    // Usage counters: the public "builds generated" figure on the home page, and
    // the internal question of whether the build tools get used at all.
    void trackEvent(mode === "counter" ? "counter_generated" : "build_generated");

    return NextResponse.json(
      { ...data, quota, cached: false },
      { headers: { "X-RateLimit-Remaining": String(quota.remaining), "X-Build-Cache": "miss" } },
    );
  } finally {
    await release();
  }
}

export async function POST(request: Request) {
  try {
    return await handlePost(request);
  } catch (error) {
    console.error("Build route failed", error);
    return NextResponse.json(
      { error: "The build service hit an unexpected error. Please try again." },
      { status: 500 },
    );
  }
}
