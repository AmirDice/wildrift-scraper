import { spawn } from "node:child_process";
import path from "node:path";
import { cookies } from "next/headers";
import { NextResponse, after } from "next/server";
import { SESSION_COOKIE, readSession, isAdmin } from "@/lib/session";
import { ACCESS_COOKIE, readAccessCookie } from "@/lib/access";
import { clientIp, consumeQuota } from "@/lib/quota";
import { trackEvent } from "@/lib/stats";

/**
 * "Why not this item?" -- challenge the generator about one absent item.
 *
 * POST { champion, items[], boots, runes[], candidate, playstyle, buildBias }
 * -> { verdict, answer, competesWith, candidateName, quota }
 *
 * A question COSTS ONE GENERATION from the same daily allowance builds use.
 * It is a real model call, and the allowance exists to measure demand rather
 * than to bill for compute, so a served answer counts exactly like a served
 * build. This also means the endpoint cannot be farmed as a free LLM.
 *
 * No cache: the question depends on the exact build in front of the player,
 * and the same candidate against a different five items is a different
 * question. Cheap enough (a few sentences, not a whole generation prompt)
 * that caching would save little and stale easily.
 */

export const maxDuration = 120;
const TIMEOUT_MS = 110_000;

const REPO_ROOT = path.resolve(process.cwd(), "..");
const ADVISOR_URL = process.env.ADVISOR_URL
  || (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}/api/advisor` : "");
const ADVISOR_SECRET = process.env.ADVISOR_SECRET || "";

/** Same PATH walk as the build route: the bare name "python" resolves to the
 *  Microsoft Store's zero-byte alias on Windows and spawn throws EPERM. */
function resolvePython(): string {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  return process.platform === "win32" ? "python.exe" : "python3";
}
const PY = resolvePython();

const BIAS_VALUES = new Set(["max_durability", "durability", "balanced", "damage", "max_damage"]);

const slug = (v: unknown) =>
  typeof v === "string" ? v.replace(/[^a-z0-9-]/g, "").slice(0, 60) : "";

/** A CONDITION, not a name: "when the enemy stacks armour" is a sentence, so
 *  it keeps sentence punctuation and a sentence-sized budget. "+" and "="
 *  survive too, because conditions read "2+ healers" and "armour >= 100". */
const condition = (v: unknown) =>
  typeof v === "string" ? v.replace(/[^A-Za-z0-9 .,:;'&%()/+=-]/g, "").slice(0, 160) : "";

const rows = (value: unknown) =>
  Array.isArray(value)
    ? value.filter((r): r is Record<string, unknown> => !!r && typeof r === "object").slice(0, 6)
    : [];

/** Situational swaps as the advisor wants them. */
const itemSwaps = (value: unknown) =>
  rows(value)
    .map((r) => ({ item: slug(r.item), replaces: slug(r.replaces), when: condition(r.when) }))
    .filter((r) => r.item);

const bootSwaps = (value: unknown) =>
  rows(value)
    .map((r) => ({ boots: slug(r.boots), when: condition(r.when) }))
    .filter((r) => r.boots);

type WhyNotResult = {
  verdict?: string;
  answer?: string;
  competesWith?: string | null;
  candidateName?: string;
  error?: string;
};

function localWhyNot(champion: string, payload: Record<string, unknown>): Promise<WhyNotResult> {
  return new Promise((resolve) => {
    const args = [
      "-m", "web.build_advisor",
      "--champion", champion,
      "--why-not", JSON.stringify(payload),
    ];
    let out = "";
    let err = "";
    let settled = false;
    const done = (value: WhyNotResult) => {
      if (!settled) { settled = true; resolve(value); }
    };
    let proc: ReturnType<typeof spawn>;
    try {
      proc = spawn(PY, args, { cwd: REPO_ROOT, env: { ...process.env, PYTHONUTF8: "1" } });
    } catch (error) {
      done({ error: `advisor process could not start: ${error instanceof Error ? error.message : String(error)}` });
      return;
    }
    const timer = setTimeout(() => { proc.kill(); done({ error: "the question timed out; ask again" }); }, TIMEOUT_MS);
    proc.stdout?.on("data", (d) => { out += d; });
    proc.stderr?.on("data", (d) => { err += d; });
    proc.on("error", (error) => { clearTimeout(timer); done({ error: String(error) }); });
    proc.on("close", () => {
      clearTimeout(timer);
      // The answer is the LAST JSON line: the advisor logs progress lines
      // above it on stdout in some configurations.
      const lines = out.trim().split(/\r?\n/).reverse();
      for (const line of lines) {
        try { done(JSON.parse(line) as WhyNotResult); return; } catch { /* keep looking */ }
      }
      done({ error: `advisor returned no answer${err ? `: ${err.slice(0, 200)}` : ""}` });
    });
  });
}

async function remoteWhyNot(champion: string, payload: Record<string, unknown>): Promise<WhyNotResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(ADVISOR_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(ADVISOR_SECRET ? { "x-advisor-secret": ADVISOR_SECRET } : {}),
      },
      body: JSON.stringify({ champion, whyNot: payload }),
      signal: controller.signal,
    });
    const data = (await res.json()) as WhyNotResult;
    if (!res.ok && !data.error) return { error: `advisor error (HTTP ${res.status})` };
    return data;
  } catch (error) {
    return { error: error instanceof Error && error.name === "AbortError"
      ? "the question timed out; ask again"
      : `advisor unreachable: ${error instanceof Error ? error.message : String(error)}` };
  } finally {
    clearTimeout(timer);
  }
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const clean = (s: unknown) =>
    typeof s === "string" ? s.replace(/[^A-Za-z0-9 .'&-]/g, "").slice(0, 40) : "";
  const champion = clean(body.champion);
  const candidate = typeof body.candidate === "string"
    ? body.candidate.replace(/[^a-z0-9-]/g, "").slice(0, 60) : "";
  if (!champion || !candidate) {
    return NextResponse.json({ error: "champion and candidate are required" }, { status: 400 });
  }
  const list = (a: unknown, limit: number) =>
    Array.isArray(a) ? a.filter((x): x is string => typeof x === "string").slice(0, limit) : [];
  const rawBias = typeof body.buildBias === "string" && BIAS_VALUES.has(body.buildBias)
    ? body.buildBias : "balanced";
  const payload = {
    items: list(body.items, 6).map((s) => s.replace(/[^a-z0-9-]/g, "").slice(0, 60)),
    boots: typeof body.boots === "string" ? body.boots.replace(/[^a-z0-9-]/g, "").slice(0, 60) : "",
    // NOT `clean`: rune names carry colons ("Legend: Alacrity") and clean
    // would eat them, degrading the context the model reasons against.
    runes: list(body.runes, 6).map((s) =>
      s.replace(/[^A-Za-z0-9 .:'&-]/g, "").slice(0, 40)),
    candidate,
    playstyle: clean(body.playstyle) || "standard",
    buildBias: rawBias,
    // The build's own situational swaps. Without them the answer could argue
    // an item down as "worse here" while the page above already offers it as
    // a swap; the advisor clamps that case to a SITUATIONAL verdict.
    situational: itemSwaps(body.situational),
    situationalBoots: bootSwaps(body.situationalBoots),
  };

  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const access = readAccessCookie(store.get(ACCESS_COOKIE)?.value);
  const unlimited = (access?.unlimited ?? false) || isAdmin(user);
  const ip = clientIp(request);
  const { ok, quota } = await consumeQuota(user, ip, unlimited);
  if (!ok) {
    return NextResponse.json(
      { error: `That is your ${quota.limit} free generations for today; a question costs one like a build does.`, quota },
      { status: 429 },
    );
  }
  after(() => trackEvent("why_not_asked"));

  const result = ADVISOR_URL && process.env.VERCEL
    ? await remoteWhyNot(champion, payload)
    : await localWhyNot(champion, payload);

  if (result.error) {
    return NextResponse.json({ error: result.error, quota }, { status: 400 });
  }
  return NextResponse.json({ ...result, quota });
}
