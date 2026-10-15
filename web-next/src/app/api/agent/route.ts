import crypto from "node:crypto";
import { spawn } from "node:child_process";
import { readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import path from "node:path";
import { cookies } from "next/headers";
import { NextResponse, after } from "next/server";
import { ACCESS_COOKIE, readAccessCookie } from "@/lib/access";
import {
  ANON_DAILY_AGENT_QUESTIONS,
  SIGNED_IN_DAILY_AGENT_QUESTIONS,
  consumeAgentQuota,
  peekAgentQuota,
  refundAgentQuota,
} from "@/lib/agent-quota";
import { buildAgentContext, championSlugFromQuestion, resolveAgentAnswer } from "@/lib/agent-context";
import type { AgentHistoryMessage } from "@/lib/agent-types";
import { clientIp } from "@/lib/quota";
import { kvGetJson, kvSetJson } from "@/lib/kv";
import { CURRENT_PATCH } from "@/lib/patch";
import { isAdmin, readSession, SESSION_COOKIE } from "@/lib/session";
import { trackEvent } from "@/lib/stats";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 90;

const REPO_ROOT = path.resolve(process.cwd(), "..");
const ADVISOR_URL = process.env.ADVISOR_URL
  || (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}/api/advisor` : "");
const ADVISOR_SECRET = process.env.ADVISOR_SECRET || "";
const TIMEOUT_MS = Math.max(10_000, Number(process.env.AGENT_TIMEOUT_MS ?? 60_000) || 60_000);
const AGENT_CACHE_TTL_SECONDS = 12 * 60 * 60;
const PUBLIC_ERROR = "The WRTrueMeta agent is temporarily unavailable. Please try again later.";

type Body = {
  question?: unknown;
  pathname?: unknown;
  championSlug?: unknown;
  history?: unknown;
};

type RunResult =
  | { ok: true; data: { answer?: unknown; evidence?: unknown; followUps?: unknown } }
  | { ok: false; refundable?: boolean };

type CachedAgentAnswer = {
  answer: string;
  evidence: string[];
  followUps: string[];
  actions: { label: string; href: string }[];
};

function cleanText(value: unknown, limit: number): string {
  if (typeof value !== "string") return "";
  return value.replace(/[\u0000-\u001f\u007f]/g, " ").replace(/\s+/g, " ").trim().slice(0, limit);
}

function cleanHistory(value: unknown): AgentHistoryMessage[] {
  if (!Array.isArray(value)) return [];
  return value.slice(-6).flatMap((entry) => {
    if (!entry || typeof entry !== "object") return [];
    const raw = entry as { role?: unknown; content?: unknown };
    const role = raw.role === "user" || raw.role === "assistant" ? raw.role : null;
    const content = cleanText(raw.content, 600);
    return role && content ? [{ role, content }] : [];
  });
}

function agentCacheKey(question: string, context: ReturnType<typeof buildAgentContext>): string {
  // Include the page, named champion and collection dates so a deploy or fresh
  // regional scrape naturally gets a new answer without storing the full data
  // snapshot in the key itself.
  // v4: the context now carries the tier list by role, the latest patch,
  // items, runes and China's loadouts, so v3 answers were made with less.
  // The patch is in the key because an answer about "the latest patch" is
  // wrong the moment the next one lands, and the TTL is twelve hours.
  const identity = JSON.stringify({
    v: 4,
    patch: CURRENT_PATCH,
    question: question.toLowerCase().replace(/\s+/g, " ").trim(),
    page: context.page,
    champion: context.championSlug ?? "",
    collected: context.site.regions.map((region) => [region.region, region.collectedOn, region.playerPoolPerChampion]),
  });
  return `cache:agent:answer:${crypto.createHash("sha256").update(identity).digest("hex").slice(0, 32)}`;
}

function resolvePython(): string {
  if (process.env.PYTHON_BIN) return process.env.PYTHON_BIN;
  const win = process.platform === "win32";
  const names = win ? ["python.exe", "python3.exe"] : ["python3", "python"];
  const real = (candidate: string) => {
    try { return statSync(candidate).size > 0 ? candidate : null; } catch { return null; }
  };
  for (const dir of (process.env.PATH ?? "").split(path.delimiter)) {
    if (!dir || (win && dir.toLowerCase().includes("microsoft\\windowsapps"))) continue;
    for (const name of names) {
      const hit = real(path.join(dir, name));
      if (hit) return hit;
    }
  }
  if (win) {
    const local = path.join(homedir(), "AppData", "Local");
    for (const root of [path.join(local, "Programs", "Python"), process.env.ProgramFiles ?? "C:\\Program Files"]) {
      let entries: string[] = [];
      try { entries = readdirSync(root).filter((entry) => entry.toLowerCase().startsWith("python")); } catch { continue; }
      for (const entry of entries.sort().reverse()) {
        const hit = real(path.join(root, entry, "python.exe"));
        if (hit) return hit;
      }
    }
  }
  return win ? "python" : "python3";
}

async function callRemote(payload: object): Promise<RunResult> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const response = await fetch(ADVISOR_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(ADVISOR_SECRET ? { "x-advisor-secret": ADVISOR_SECRET } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) return { ok: false, refundable: response.status === 404 };
    return { ok: true, data: await response.json() as RunResult extends { ok: true; data: infer T } ? T : never };
  } catch {
    return { ok: false };
  } finally {
    clearTimeout(timer);
  }
}

function callLocal(payload: object): Promise<RunResult> {
  return new Promise((resolve) => {
    let child: ReturnType<typeof spawn>;
    let started = false;
    let settled = false;
    let stdout = "";
    const finish = (result: RunResult) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(result);
    };
    const timer = setTimeout(() => {
      finish({ ok: false });
      try { child.kill(); } catch { /* already settled */ }
    }, TIMEOUT_MS);
    try {
      child = spawn(resolvePython(), ["-m", "web.site_agent"], {
        cwd: REPO_ROOT,
        env: { ...process.env, PYTHONUTF8: "1" },
      });
    } catch {
      finish({ ok: false, refundable: true });
      return;
    }
    child.once("spawn", () => { started = true; });
    child.once("error", () => finish({ ok: false, refundable: !started }));
    child.stdout?.on("data", (chunk) => { stdout += String(chunk); });
    child.on("close", (code) => {
      if (code !== 0) return finish({ ok: false });
      try {
        finish({ ok: true, data: JSON.parse(stdout) });
      } catch {
        finish({ ok: false });
      }
    });
    child.stdin?.end(JSON.stringify(payload));
  });
}

function runAgent(payload: object): Promise<RunResult> {
  return ADVISOR_URL ? callRemote(payload) : callLocal(payload);
}

function modelActions(context: ReturnType<typeof buildAgentContext>) {
  if (context.champion) return [
    { label: "Open champion profile", href: `/champions/${context.champion.slug}` },
    { label: "Open Build Studio", href: `/build?champion=${context.champion.slug}&tab=generate` },
  ];
  if (context.page === "tier list") return [
    { label: "Open tier list", href: "/tier-list" },
    { label: "Read methodology", href: "/methodology" },
  ];
  if (context.page === "leaderboard") return [
    { label: "Open leaderboard", href: "/leaderboard" },
    { label: "Read methodology", href: "/methodology" },
  ];
  if (context.page === "meta overview") return [
    { label: "Open meta overview", href: "/meta" },
    { label: "Compare regions", href: "/regions" },
  ];
  if (context.page === "item catalogue") return [{ label: "Open items", href: "/items" }];
  if (context.page === "runes and spells") return [{ label: "Open runes and spells", href: "/runes-spells" }];
  if (context.page === "Build Studio") return [{ label: "Open Build Studio", href: "/build" }];
  return [
    { label: "Explore tier list", href: "/tier-list" },
    { label: "Read methodology", href: "/methodology" },
  ];
}

async function identity(request: Request) {
  const store = await cookies();
  const user = readSession(store.get(SESSION_COOKIE)?.value);
  const access = readAccessCookie(store.get(ACCESS_COOKIE)?.value);
  return { user, ip: clientIp(request), unlimited: Boolean(access?.unlimited || isAdmin(user)) };
}

export async function GET(request: Request) {
  const { user, ip, unlimited } = await identity(request);
  const quota = await peekAgentQuota(user, ip, unlimited);
  return NextResponse.json({ quota }, { headers: { "Cache-Control": "private, no-store, max-age=0" } });
}

export async function POST(request: Request) {
  let body: Body;
  try { body = await request.json(); } catch {
    return NextResponse.json({ error: "Invalid request." }, { status: 400 });
  }
  const question = cleanText(body.question, 500);
  if (!question) return NextResponse.json({ error: "Ask a question first." }, { status: 400 });
  const pathname = cleanText(body.pathname, 160) || "/";
  const championSlug = cleanText(body.championSlug, 60).toLowerCase().replace(/[^a-z0-9-]/g, "");
  // A named champion wins over the page champion: asking about Caitlyn while
  // reading Jinx should not silently ground the answer in Jinx's data.
  const context = buildAgentContext(pathname, championSlugFromQuestion(question) || championSlug, question);

  const grounded = resolveAgentAnswer(question, context);
  if (grounded) {
    after(() => trackEvent("agent_data_answered"));
    return NextResponse.json(grounded, { headers: { "Cache-Control": "private, no-store, max-age=0" } });
  }

  const cacheKey = agentCacheKey(question, context);
  const cached = await kvGetJson<CachedAgentAnswer | null>(cacheKey, null);
  if (cached?.answer) {
    const { user, ip, unlimited } = await identity(request);
    const quota = await peekAgentQuota(user, ip, unlimited);
    after(() => trackEvent("agent_cache_hit"));
    return NextResponse.json({ ...cached, source: "model", quota }, { headers: { "Cache-Control": "private, no-store, max-age=0" } });
  }

  const { user, ip, unlimited } = await identity(request);
  const allowance = await consumeAgentQuota(user, ip, unlimited);
  if (!allowance.ok) {
    after(() => trackEvent("agent_limit_reached"));
    const hours = Math.max(1, Math.ceil((allowance.quota.resetAt - Date.now()) / 3_600_000));
    return NextResponse.json({
      error: allowance.quota.canUnlockBySigningIn
        ? `Your free AI question is used. Sign in for ${SIGNED_IN_DAILY_AGENT_QUESTIONS} per day, or try again in ~${hours}h. Site-data questions remain unlimited.`
        : `Daily AI question limit reached (${allowance.quota.limit}/day). It resets in ~${hours}h. Site-data questions remain unlimited.`,
      quota: allowance.quota,
    }, { status: 429, headers: { "Cache-Control": "private, no-store, max-age=0" } });
  }

  const history = cleanHistory(body.history);
  const result = await runAgent({ task: "site-agent", question, context, history });
  if (!result.ok) {
    const quota = result.refundable
      ? await refundAgentQuota(user, ip, unlimited)
      : allowance.quota;
    return NextResponse.json({ error: PUBLIC_ERROR, quota }, { status: 502 });
  }

  const answer = cleanText(result.data.answer, 2_400);
  if (!answer) return NextResponse.json({ error: PUBLIC_ERROR, quota: allowance.quota }, { status: 502 });
  after(() => trackEvent("agent_model_answered"));
  const response = {
    answer,
    source: "model",
    evidence: Array.isArray(result.data.evidence)
      ? result.data.evidence.map((entry) => cleanText(entry, 240)).filter(Boolean).slice(0, 4)
      : [],
    followUps: Array.isArray(result.data.followUps)
      ? result.data.followUps.map((entry) => cleanText(entry, 160)).filter(Boolean).slice(0, 3)
      : [],
    actions: modelActions(context),
    quota: allowance.quota,
  };
  const cacheEntry: CachedAgentAnswer = {
    answer,
    evidence: response.evidence,
    followUps: response.followUps,
    actions: response.actions,
  };
  after(async () => {
    try { await kvSetJson(cacheKey, cacheEntry, AGENT_CACHE_TTL_SECONDS); } catch { /* caching is best effort */ }
  });
  return NextResponse.json(response, { headers: { "Cache-Control": "private, no-store, max-age=0" } });
}

