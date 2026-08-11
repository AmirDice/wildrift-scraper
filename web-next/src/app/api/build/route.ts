import { spawn } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { cookies } from "next/headers";
import { NextResponse, after } from "next/server";
import { SESSION_COOKIE, readSession, isAdmin } from "@/lib/session";
import { ACCESS_COOKIE, readAccessCookie } from "@/lib/access";
import { ANON_DAILY_BUILDS, clientIp, consumeQuota, peekQuota, quotaIdentity, refundQuota, type QuotaState } from "@/lib/quota";
import { buildCacheKey, readCachedBuild, writeCachedBuild } from "@/lib/build-cache";
import { checkAbuseGuards } from "@/lib/build-guards";
import { recordGenerationEngagement, trackEvent } from "@/lib/stats";

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

/**
 * A Python that can actually be executed.
 *
 * Spawning the bare name "python" resolves through PATH, and on Windows the
 * first hit is usually the Microsoft Store app-execution alias in
 * %LOCALAPPDATA%\Microsoft\WindowsApps -- a ZERO-BYTE reparse stub that exists
 * to open the Store. Node cannot execute it and spawn throws EPERM, which
 * surfaced as "advisor process could not start: spawn EPERM" with the real
 * interpreter sitting further down the same PATH.
 *
 * So: walk PATH ourselves, skip the aliases, and take the first real binary.
 * PYTHON_BIN still wins if it is set.
 */
function resolvePython(): string {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  const win = process.platform === "win32";
  const names = win ? ["python.exe", "python3.exe"] : ["python3", "python"];
  const real = (candidate: string) => {
    try {
      // A stub alias reports size 0; a real interpreter never does.
      return statSync(candidate).size > 0 ? candidate : null;
    } catch {
      return null;
    }
  };

  for (const dir of (process.env.PATH ?? "").split(path.delimiter)) {
    if (!dir) continue;
    if (win && dir.toLowerCase().includes("microsoft\\windowsapps")) continue;
    for (const name of names) {
      const hit = real(path.join(dir, name));
      if (hit) return hit;
    }
  }

  // PATH is not enough. A dev server started from Explorer or a shell profile
  // that never ran the Python installer's PATH edit inherits an environment
  // where the interpreter simply is not on PATH -- which is the case on the
  // machine this was reported from -- so look where Windows actually puts it.
  if (win) {
    // Derived from the home directory rather than %LOCALAPPDATA%, because the
    // env the dev server inherits does not reliably carry it -- when it was
    // missing this fell through to py.exe, which answered "No installed Python
    // found!" for a user-scoped install it cannot see.
    const local = path.join(homedir(), "AppData", "Local");
    const roots = [
      path.join(local, "Programs", "Python"),
      path.join(process.env.LOCALAPPDATA ?? local, "Programs", "Python"),
      process.env.ProgramFiles ?? "C:\\Program Files",
      "C:\\",
    ];
    for (const root of roots) {
      let entries: string[] = [];
      try {
        entries = readdirSync(root).filter((d) => d.toLowerCase().startsWith("python"));
      } catch {
        continue;
      }
      // Newest first, so a machine with several versions uses the current one.
      for (const dir of entries.sort().reverse()) {
        const hit = real(path.join(root, dir, "python.exe"));
        if (hit) return hit;
      }
    }
    // The launcher ships with every standard install and resolves versions
    // itself. Last resort because it needs no PATH entry at all.
    const launcher = real(path.join(process.env.WINDIR ?? "C:\\Windows", "py.exe"));
    if (launcher) return launcher;
  }
  return win ? "python" : "python3";
}

const PY = resolvePython();
// Thinking-mode generations now include the mandatory item audit and complete
// LLM build evaluation, so allow the same four-minute ceiling as the advisor.
const TIMEOUT_MS = 240_000;
// Set on Vercel; absent locally, which is what selects the subprocess path.
const ADVISOR_URL = process.env.ADVISOR_URL
  || (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}/api/advisor` : "");
const ADVISOR_SECRET = process.env.ADVISOR_SECRET || "";

// The daily cap lives in src/lib/quota.ts: 5 generations per IP per day, plus
// another 5 for anyone signed in with Google. It exists because every
// generation costs a real model call, so an unattended script could otherwise
// run up the bill.

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
  skillLevel?: string;
  lockedItems?: string[];
  lockedRunes?: string[];
  /** How many times to sample the model before answering. Set by this route on
   *  a cache miss, never by the client. */
  runs?: number;
};

/**
 * Samples per generation, on a cache miss. OFF by default.
 *
 * The machinery is built and tested (advise_best_of, tests/test_consensus.py):
 * sample the model N times in parallel, keep the build the samples agree on.
 * It exists because a cache miss is the generation that becomes that request's
 * answer for everyone until the patch rolls, so a bad draw gets frozen in.
 *
 * It is not switched on because the model we actually run does not draw badly.
 * Measured on Vayne at five samples on gemini-3.6-flash: nine of ten build
 * elements unanimous, all four runes identical in every sample, and a single
 * unsampled run returned the same five items the vote did -- matching the
 * top-50 ladder core exactly. There is nothing for a vote to correct. Five
 * samples also drew a 503 from the provider under concurrency, so switching it
 * on would trade a real failure mode for a hypothetical one.
 *
 * Worth revisiting if the model changes, or for a champion whose builds
 * genuinely fork. BUILD_CONSENSUS_RUNS=5 turns it on with no code change; the
 * advisor clamps to 5 whatever this says. Counter mode stays at one either
 * way: it is wanted fast and the enemy comp already constrains the answer.
 */
const CONSENSUS_RUNS = Math.max(1, Number(process.env.BUILD_CONSENSUS_RUNS ?? 1) || 1);

/**
 * The response for "you have nothing left today", shared by the cache path and
 * the generation path so a player gets the same answer either way.
 *
 * Recording the refusal is the point: the depth histogram counts generations
 * that HAPPENED, so demand above the ceiling is invisible unless the block
 * itself is counted. Split by whether signing in would still unlock more,
 * because those are different decisions -- one is a conversion prompt that is
 * not working, the other is a cap costing real usage.
 */
function outOfAllowance(quota: QuotaState): NextResponse {
  after(() => trackEvent(quota.canUnlockBySigningIn ? "limit_reached_anon" : "limit_reached_signed_in"));
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

type AdvisorResult =
  | { ok: true; data: unknown }
  | {
      ok: false;
      error: string;
      /** True only when the request is confirmed never to have reached the
       *  model: the local advisor did not start, or the remote one is absent.
       *  A failure that may have spent a model call must not be refunded. */
      quotaRefundable?: boolean;
    };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Turn whatever the advisor endpoint returned into something a player can read.
 *
 * Our own function answers with `{"error": "some text"}`. Vercel's PLATFORM
 * errors also answer with JSON, but the error is an object:
 * `{"error": {"code": "NOT_FOUND", "message": "..."}}`. That shape used to be
 * interpolated straight into the response, so a missing advisor surfaced in the
 * UI as the immortal "Could not build: [object Object] (HTTP 502)".
 */
function advisorErrorText(data: unknown, status: number): string {
  const raw = (data as { error?: unknown })?.error;
  if (typeof raw === "string" && raw.trim()) return raw.trim();

  if (raw && typeof raw === "object") {
    const { code, message } = raw as { code?: unknown; message?: unknown };
    if (code === "NOT_FOUND" || status === 404) {
      return "the build service is not deployed in this environment yet";
    }
    const parts = [code, message].filter((p): p is string => typeof p === "string" && !!p);
    if (parts.length) return parts.join(": ");
  }

  if (status === 404) return "the build service is not deployed in this environment yet";
  return `the build service returned ${status}`;
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
      // A 404 that is not even JSON means the request fell through to the
      // Next app's own not-found page, i.e. the Python function is not there.
      // Dumping 300 characters of HTML at the player helps nobody.
      if (res.status === 404) {
        return { ok: false, error: advisorErrorText(null, 404), quotaRefundable: true };
      }
      return { ok: false, error: `unparseable advisor response: ${text.slice(0, 300)}` };
    }
    if (!res.ok) {
      // A 404 never reached the model, so it must not cost the player a
      // generation from their daily allowance.
      return {
        ok: false,
        error: advisorErrorText(data, res.status),
        quotaRefundable: res.status === 404,
      };
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
      "--skill-level",
      b.skillLevel ?? "average",
      "--locked-items",
      (b.lockedItems ?? []).join(","),
      "--locked-runes",
      (b.lockedRunes ?? []).join(","),
      "--runs",
      String(b.runs ?? 1),
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
        // Name the interpreter. A failure here is usually about WHICH python
        // ran, not about the advisor, and without this the message sends you
        // looking in the wrong place.
        finish({ ok: false, error: `${err.trim() || `advisor exited ${code}`} [python: ${PY}]` });
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
  // Either route to an exempt account: an access code's cookie, or being one of
  // the ADMIN_EMAILS. Usage is still counted for both (see consumeQuota), so
  // the cost of a beta remains visible.
  const unlimited = (access?.unlimited ?? false) || isAdmin(user);

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
    skillLevel: clean(body.skillLevel) || "average",
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
    const cacheIp = clientIp(request);
    // A cache hit spends an allowance exactly like a fresh generation.
    //
    // It used to be free, on the reasoning that a lookup costs us nothing and
    // charging for it charges for work we did not do. That is true about COST
    // and wrong about MEASUREMENT, which is what the allowance is really for
    // here: nothing is being sold, so the five-a-day exists to tell us how
    // much people want. Free cache hits meant a heavy user could take twenty
    // builds a day, never reach the cap, and register as ordinary -- hiding
    // exactly the person worth learning about before there is anything to
    // monetise. Owner's call, 2026-08-09.
    const { ok, quota } = await consumeQuota(user, cacheIp, unlimited);
    if (!ok) return outOfAllowance(quota);
    after(() => trackEvent(mode === "counter" ? "counter_generated" : "build_generated"));
    // Real depth now, not null: the allowance WAS consumed, so this belongs in
    // the distribution the "used all five" figure is read from.
    after(() => recordGenerationEngagement(quotaIdentity(user, cacheIp), quota.used));
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
    if (!ok) return outOfAllowance(quota);

    const res = await runAdvisor({
      ...advisorRequest,
      runs: mode === "counter" ? 1 : CONSENSUS_RUNS,
    });
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
    after(() => trackEvent(mode === "counter" ? "counter_generated" : "build_generated"));
    // Engagement: quota.used IS this generation's depth into the daily
    // allowance (1..5, 6+ for unlimited), so the distribution of "stopped at
    // one" vs "burned all five" and the new-vs-returning split fall straight
    // out of the number we already have. Recorded only on success, so a
    // refunded infrastructure failure never counts as usage.
    after(() => recordGenerationEngagement(quotaIdentity(user, ip), quota.used));

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
