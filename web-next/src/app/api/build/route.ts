import { spawn } from "node:child_process";
import path from "node:path";
import { NextResponse } from "next/server";

/**
 * Live build advisor. POST { champion, role, enemies[], allies[], playstyle }
 * -> the validated JSON build from web/build_advisor.py.
 *
 * The whole data pipeline (items, runes, matchups, meta, the scoring engine for
 * the cross-check) lives in Python, so the route SPAWNS the advisor rather than
 * re-implementing it in TS. Acceptable for launch traffic; swap for a persistent
 * Python service if request volume grows.
 */
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// repo root = parent of the web-next dir this app runs from
const REPO_ROOT = path.resolve(process.cwd(), "..");
const PY = process.env.PYTHON_BIN || "python";
const TIMEOUT_MS = 90_000;

// Per-IP daily cap. We are not gating behind auth at launch (the cost per build
// is ~$0.003), but this stops a script from running up the DeepSeek bill. Set
// via BUILD_LIMIT_PER_DAY; defaults to 5. In-memory, so it resets on redeploy
// and does NOT share across instances -- fine for a single-server launch; move
// to Redis/KV when the app scales horizontally.
const DAILY_LIMIT = Number(process.env.BUILD_LIMIT_PER_DAY) || 5;
const WINDOW_MS = 24 * 60 * 60 * 1000;
const hits = new Map<string, { count: number; resetAt: number }>();

function rateLimit(ip: string): { ok: boolean; remaining: number; resetAt: number } {
  const now = Date.now();
  const rec = hits.get(ip);
  if (!rec || now > rec.resetAt) {
    const fresh = { count: 1, resetAt: now + WINDOW_MS };
    hits.set(ip, fresh);
    return { ok: true, remaining: DAILY_LIMIT - 1, resetAt: fresh.resetAt };
  }
  if (rec.count >= DAILY_LIMIT) {
    return { ok: false, remaining: 0, resetAt: rec.resetAt };
  }
  rec.count += 1;
  return { ok: true, remaining: DAILY_LIMIT - rec.count, resetAt: rec.resetAt };
}

function clientIp(request: Request): string {
  const xff = request.headers.get("x-forwarded-for");
  if (xff) return xff.split(",")[0].trim();
  return request.headers.get("x-real-ip") || "unknown";
}

type Body = {
  champion?: string;
  role?: string;
  enemies?: string[];
  allies?: string[];
  playstyle?: string;
  objective?: string;
};

function runAdvisor(b: Body): Promise<{ ok: boolean; data?: unknown; error?: string }> {
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
    ];
    const proc = spawn(PY, args, {
      cwd: REPO_ROOT,
      env: { ...process.env, PYTHONUTF8: "1" },
    });

    let out = "";
    let err = "";
    const timer = setTimeout(() => {
      proc.kill();
      resolve({ ok: false, error: "advisor timed out" });
    }, TIMEOUT_MS);

    proc.stdout.on("data", (d) => (out += d));
    proc.stderr.on("data", (d) => (err += d));
    proc.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        resolve({ ok: false, error: err.trim() || `advisor exited ${code}` });
        return;
      }
      try {
        resolve({ ok: true, data: JSON.parse(out) });
      } catch {
        resolve({ ok: false, error: `unparseable advisor output: ${out.slice(0, 300)}` });
      }
    });
  });
}

export async function POST(request: Request) {
  let body: Body;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  if (!body.champion || typeof body.champion !== "string") {
    return NextResponse.json({ error: "champion is required" }, { status: 400 });
  }
  const rl = rateLimit(clientIp(request));
  if (!rl.ok) {
    const hrs = Math.ceil((rl.resetAt - Date.now()) / 3_600_000);
    return NextResponse.json(
      { error: `Daily build limit reached (${DAILY_LIMIT}/day). Resets in ~${hrs}h. Support the site to lift the cap soon!` },
      { status: 429 },
    );
  }
  // guard the shell-out: only plausible names/values reach argv
  const clean = (s: unknown) =>
    typeof s === "string" ? s.replace(/[^A-Za-z0-9 .'&-]/g, "").slice(0, 40) : "";
  const cleanList = (a: unknown) =>
    Array.isArray(a) ? a.map(clean).filter(Boolean).slice(0, 5) : [];

  const res = await runAdvisor({
    champion: clean(body.champion),
    role: clean(body.role),
    enemies: cleanList(body.enemies),
    allies: cleanList(body.allies),
    playstyle: clean(body.playstyle) || "standard",
    objective: clean(body.objective) || "balanced",
  });

  if (!res.ok) {
    return NextResponse.json({ error: res.error }, { status: 502 });
  }
  return NextResponse.json(res.data, {
    headers: { "X-RateLimit-Remaining": String(rl.remaining) },
  });
}
