import { NextResponse } from "next/server";
import championDetailsData from "@/data/champion_details.json";
import engineData from "@/data/engine.json";
import itemData from "@/data/items.json";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DEEPSEEK_URL = "https://api.deepseek.com/chat/completions";
const MODEL = "deepseek-v4-flash";
const TIMEOUT_MS = 240_000;

type StatValue = { value?: number; percent?: boolean } | number;
type ItemRow = {
  slug: string;
  name: string;
  cost: number;
  stats?: Record<string, StatValue>;
  scopedStats?: Record<string, StatValue>;
  passives?: string[];
};
type Ability = { slot?: string; name?: string; text?: string };
type ChampionDetail = { name?: string; abilities?: Ability[] };
type SubmittedBuild = { label?: string; itemSlugs?: string[]; runeNames?: string[] };
type Body = { champion?: string; goal?: string; left?: SubmittedBuild; right?: SubmittedBuild };

const ITEMS = new Map((itemData as unknown as ItemRow[]).map((item) => [item.slug, item]));
const CHAMPIONS = championDetailsData as Record<string, ChampionDetail>;
const RUNES = (engineData as { runes?: Record<string, { description?: string }> }).runes ?? {};
const GOALS: Record<string, string> = {
  overall: "highest practical win rate in a typical 15-20 minute Wild Rift match",
  burst: "fastest reliable burst and target deletion",
  sustained: "best sustained damage in an extended fight",
  survivability: "best ability to survive focus and continue contributing",
  early: "strongest early and mid-game power curve",
};

function cleanText(value: unknown, max = 60): string {
  return typeof value === "string" ? value.replace(/[^A-Za-z0-9 .'&:+%-]/g, "").slice(0, max) : "";
}

function cleanBuild(value: SubmittedBuild | undefined): SubmittedBuild {
  return {
    label: cleanText(value?.label, 80),
    itemSlugs: Array.isArray(value?.itemSlugs)
      ? value.itemSlugs.map((slug) => cleanText(slug, 60)).filter(Boolean).slice(0, 6)
      : [],
    runeNames: Array.isArray(value?.runeNames)
      ? value.runeNames.map((name) => cleanText(name, 60)).filter(Boolean).slice(0, 5)
      : [],
  };
}

function statText(stats: Record<string, StatValue> | undefined): string {
  return Object.entries(stats ?? {}).map(([key, raw]) => {
    const value = typeof raw === "number" ? raw : raw.value ?? 0;
    const percent = typeof raw === "number" ? false : Boolean(raw.percent);
    return `${key}=${value}${percent ? "%" : ""}`;
  }).join(", ");
}

function itemLine(slug: string): string {
  const item = ITEMS.get(slug);
  if (!item) throw new Error(`unknown item slug: ${slug}`);
  const scoped = statText(item.scopedStats);
  const passives = (item.passives ?? []).join(" | ");
  return `${item.name} (${slug}) · ${item.cost}g · ${statText(item.stats)}`
    + (scoped ? ` · scoped ${scoped}` : "")
    + (passives ? ` :: ${passives}` : "");
}

function buildBlock(side: string, build: SubmittedBuild): string {
  const slugs = build.itemSlugs ?? [];
  if (!slugs.length) throw new Error(`${side} build has no items`);
  const runes = (build.runeNames ?? []).map((name) => {
    const description = RUNES[name]?.description;
    return `  ${name}${description ? `: ${description}` : ""}`;
  });
  return [
    `${side.toUpperCase()} BUILD — ${build.label || side}`,
    "Items in purchase order:",
    ...slugs.map((slug, index) => `  ${index + 1}. ${itemLine(slug)}`),
    "Runes:",
    ...runes,
  ].join("\n");
}

function championBlock(name: string): string {
  const detail = Object.values(CHAMPIONS).find((champion) => champion.name === name);
  if (!detail) throw new Error(`unknown champion: ${name}`);
  return [
    `CHAMPION: ${name}`,
    ...(detail.abilities ?? []).map((ability) => `[${ability.slot ?? "?"}] ${ability.name ?? "Ability"}: ${ability.text ?? ""}`),
  ].join("\n");
}

async function judge(body: Required<Pick<Body, "champion" | "goal" | "left" | "right">>) {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) throw new Error("comparison service is not configured");
  const prompt = [
    championBlock(body.champion),
    `JUDGING GOAL: ${GOALS[body.goal] ?? GOALS.overall}`,
    buildBlock("left", body.left),
    buildBlock("right", body.right),
    "Judge these exact completed loadouts. Account for kit and rune synergy, purchase order, gold cost, practical 15-20 minute timing, cap waste, and conditional/passive value. Higher raw stats alone do not decide the winner. Pick a tie only when the builds are genuinely within two points. Return ONLY JSON: "
      + '{"winner":"left|right|tie","leftScore":0-100,"rightScore":0-100,"confidence":0-100,"reason":"2-3 sentence verdict","decidingFactors":["2-4 concise factors"],"tradeoff":"what the losing build does better"}',
  ].join("\n\n");
  const system = "You are a Challenger Wild Rift coach judging two exact builds. Use champion game knowledge for play patterns, but treat the supplied champion, item, rune, price, and passive data as the only current-patch facts. Average games last roughly 15-20 minutes and fights are short. Do not substitute items or runes and do not imply a fight simulation.";
  const response = await fetch(DEEPSEEK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: JSON.stringify({
      model: MODEL,
      messages: [{ role: "system", content: system }, { role: "user", content: prompt }],
      response_format: { type: "json_object" },
      thinking: { type: "enabled" },
      reasoning_effort: "high",
      temperature: 0,
      max_tokens: 384_000,
      stream: false,
    }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!response.ok) throw new Error(`comparison service returned ${response.status}`);
  const payload = await response.json() as {
    choices?: { finish_reason?: string; message?: { content?: string } }[];
  };
  const choice = payload.choices?.[0];
  if (choice?.finish_reason === "length") throw new Error("comparison response was incomplete");
  const result = JSON.parse(choice?.message?.content ?? "{}") as Record<string, unknown>;
  if (!["left", "right", "tie"].includes(String(result.winner))) throw new Error("comparison returned an invalid winner");
  return result;
}

export async function POST(request: Request) {
  let raw: Body;
  try {
    raw = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const champion = cleanText(raw.champion);
  const cleanedGoal = cleanText(raw.goal);
  const goal = cleanedGoal in GOALS ? cleanedGoal : "overall";
  const left = cleanBuild(raw.left);
  const right = cleanBuild(raw.right);
  if (!champion || !left.itemSlugs?.length || !right.itemSlugs?.length) {
    return NextResponse.json({ error: "champion and two non-empty builds are required" }, { status: 400 });
  }
  try {
    return NextResponse.json(await judge({ champion, goal, left, right }));
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : String(error) }, { status: 502 });
  }
}
