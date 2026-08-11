import { NextResponse } from "next/server";
import { kvDelete, kvGetJson, kvList, kvRightPush, kvSet } from "@/lib/kv";

/**
 * The Operations panel's API: a job queue between the admin page and the
 * ops runner on the owner's machine (scripts/ops_runner.py).
 *
 *   GET  ?token=...                      -> runner heartbeat, current job with
 *                                           its log tail, queue, history
 *   POST ?token=...  { action, ... }     -> enqueue | stop | clear-queue | reset
 *
 * Only op NAMES cross this boundary -- the mapping to actual command lines
 * lives in the runner, and both sides validate. The champion list is the one
 * free-text argument, and it is constrained to name characters here AND
 * re-checked in the runner, so this route can never be talked into running
 * anything that is not already in the runner's whitelist.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const OPS = new Set([
  "scrape", "extract-pending", "refresh-data", "fetch-patches", "publish", "deploy-advisor",
  "export-analytics",
]);

// Letters, spaces and the punctuation that occurs in champion names
// (K'Sante, Dr. Mundo, Nunu & Willump, Kai-... ) -- nothing shell-relevant.
const ONLY_OK = /^[A-Za-z'&.\- ,]{0,400}$/;

function authorised(request: Request): boolean {
  const expected = process.env.ADMIN_TOKEN ?? "";
  if (!expected) return false;
  const provided = new URL(request.url).searchParams.get("token")
    ?? request.headers.get("x-admin-token")
    ?? "";
  return provided === expected;
}

const denied = () => NextResponse.json({ error: "not found" }, { status: 404 });

interface RunnerBeat { at: number; host: string; job: { id: string; op: string } | null }

export async function GET(request: Request) {
  if (!authorised(request)) return denied();
  const [runner, current, queueRaw, historyRaw] = await Promise.all([
    kvGetJson<RunnerBeat | null>("ops:runner", null),
    kvGetJson<Record<string, unknown> | null>("ops:current", null),
    kvList("ops:queue", 50),
    kvList("ops:history", 20),
  ]);
  const parse = (raw: string) => {
    try { return JSON.parse(raw) as Record<string, unknown>; } catch { return null; }
  };
  return NextResponse.json({
    // The heartbeat carries its own clock; comparing to Date.now() here keeps
    // the online/offline call server-side where the clocks are comparable.
    runnerOnline: Boolean(runner && Date.now() / 1000 - runner.at < 20),
    runner,
    current,
    queue: queueRaw.map(parse).filter(Boolean),
    history: historyRaw.map(parse).filter(Boolean),
  }, { headers: { "Cache-Control": "private, no-store, max-age=0" } });
}

export async function POST(request: Request) {
  if (!authorised(request)) return denied();

  let body: Record<string, unknown>;
  try {
    body = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }

  const action = String(body.action ?? "");

  if (action === "stop") {
    // The runner clears the flag after the kill; the TTL covers the case
    // where nothing is running and nobody ever clears it.
    await kvSet("ops:stop", "1", 600);
    return NextResponse.json({ ok: true });
  }

  if (action === "clear-queue") {
    await kvDelete("ops:queue");
    return NextResponse.json({ ok: true });
  }

  if (action === "reset") {
    // For a runner that died mid-job and left ops:current stuck on "running".
    await Promise.all([kvDelete("ops:current"), kvDelete("ops:stop")]);
    return NextResponse.json({ ok: true });
  }

  if (action === "enqueue") {
    const op = String(body.op ?? "");
    if (!OPS.has(op)) {
      return NextResponse.json({ error: `unknown op: ${op}` }, { status: 400 });
    }
    const args: Record<string, unknown> = {};
    if (op === "scrape") {
      const only = typeof body.only === "string" ? body.only.trim() : "";
      if (only && !ONLY_OK.test(only)) {
        return NextResponse.json(
          { error: "the champion list may only contain names (letters, commas, ' & . -)" },
          { status: 400 },
        );
      }
      if (only) args.only = only;
      args.skipExisting = body.skipExisting !== false && !only;
    }
    if (op === "refresh-data" && body.fresh === true) args.fresh = true;

    const job = {
      id: crypto.randomUUID().slice(0, 10),
      op,
      args,
      queuedAt: Date.now() / 1000,
    };
    await kvRightPush("ops:queue", JSON.stringify(job));
    return NextResponse.json({ ok: true, job });
  }

  return NextResponse.json({ error: `unknown action: ${action}` }, { status: 400 });
}
