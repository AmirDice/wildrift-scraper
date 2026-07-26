import engineData from "@/data/engine.json";
import type { Champion } from "@/lib/data";

export const PLAYSTYLE_METRICS = [
  { key: "spellCastRate", label: "Spell casting", hint: "How frequently the champion relies on abilities during combat." },
  { key: "fightFrequency", label: "Fight seeking", hint: "How strongly the champion wants to start or join fights." },
  { key: "tradeFrequency", label: "Trading", hint: "How often the champion looks for short exchanges in lane." },
  { key: "roamFrequency", label: "Roaming", hint: "How much value comes from moving to other lanes and skirmishes." },
  { key: "waveclear", label: "Waveclear", hint: "How quickly and safely the champion clears minion waves." },
  { key: "objectiveDamage", label: "Objective damage", hint: "How effectively the champion helps burn turrets and neutral objectives." },
  { key: "jungleClear", label: "Jungle clear", hint: "How quickly and healthily the champion clears jungle camps." },
  { key: "avgFightLength", label: "Extended fights", hint: "How much the champion prefers long fights over short bursts." },
] as const;

export type PlaystyleMetricKey = (typeof PLAYSTYLE_METRICS)[number]["key"];
export type PlaystyleValues = Record<PlaystyleMetricKey, number>;

export interface PlaystyleProfileData {
  values: PlaystyleValues;
  confidence: "high" | "medium" | "estimated";
  source: "kit-profile" | "role-estimate";
}

type RawBehavior = Partial<Record<PlaystyleMetricKey, number>> & { confidence?: string };
type EngineShape = { formulas?: Record<string, { behavior?: RawBehavior }> };

const clamp = (value: number) => Math.max(0, Math.min(1, value));

function estimateProfile(champion: Pick<Champion, "role" | "class" | "difficulty">): PlaystyleValues {
  const role = champion.role.toLowerCase();
  const klass = champion.class.toLowerCase();
  const isTank = klass.includes("tank");
  const isMage = klass.includes("mage");
  const isAssassin = klass.includes("assassin");
  const isBruiser = klass.includes("bruiser") || klass.includes("fighter");
  const isMarksman = klass.includes("marksman") || klass.includes("adc");
  const isSupport = role.includes("support");
  const isJungle = role.includes("jungle");

  return {
    spellCastRate: isMage || isAssassin ? 0.82 : isTank || isBruiser ? 0.66 : 0.48,
    fightFrequency: isTank || isAssassin || isJungle ? 0.82 : isBruiser ? 0.7 : 0.55,
    tradeFrequency: isMarksman || isMage ? 0.72 : isSupport ? 0.58 : 0.66,
    roamFrequency: isJungle ? 0.95 : isSupport || isAssassin ? 0.78 : 0.45,
    waveclear: isMage || isMarksman ? 0.78 : isBruiser ? 0.64 : 0.48,
    objectiveDamage: isMarksman ? 0.92 : isJungle || isBruiser ? 0.7 : 0.42,
    jungleClear: isJungle ? 0.88 : isBruiser ? 0.55 : 0.3,
    avgFightLength: isTank || isBruiser ? 0.82 : isMarksman ? 0.68 : isMage ? 0.46 : 0.35,
  };
}

export function getPlaystyleProfile(champion: Pick<Champion, "name" | "role" | "class" | "difficulty">): PlaystyleProfileData {
  const raw = (engineData as unknown as EngineShape).formulas?.[champion.name]?.behavior;
  const fallback = estimateProfile(champion);
  if (!raw) return { values: fallback, confidence: "estimated", source: "role-estimate" };

  const values = Object.fromEntries(
    PLAYSTYLE_METRICS.map(({ key }) => [key, clamp(typeof raw[key] === "number" ? raw[key]! : fallback[key])]),
  ) as PlaystyleValues;
  const confidence = raw.confidence === "high" ? "high" : "medium";
  return { values, confidence, source: "kit-profile" };
}

export function playstyleLevel(value: number) {
  if (value >= 0.82) return "Very high";
  if (value >= 0.62) return "High";
  if (value >= 0.42) return "Moderate";
  if (value >= 0.22) return "Low";
  return "Very low";
}
