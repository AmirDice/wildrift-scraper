"use client";

import { useCallback, useState, useSyncExternalStore } from "react";
import { Tip } from "@/components/build-view";
import {
  calculatedChampionAbilities,
  DUAL_FORM_CHAMPIONS,
  ultTransform,
  conditionalBuildEffects,
  listedBuildStats,
  type CustomizerItem,
  type CustomizerRune,
} from "@/lib/customizer-data";
import { scaledBuildStats, scalingSources, unmodelledRunes } from "@/lib/build-scaling";

/* eslint-disable @next/next/no-img-element */

const STAT_ROWS = [
  ["ad", "Attack Damage", "text-orange-400", ""],
  ["ap", "Ability Power", "text-violet-400", ""],
  ["hp", "Health", "text-emerald-300", ""],
  ["armor", "Armor", "text-orange-300", ""],
  ["mr", "Magic Resist", "text-violet-300", ""],
  ["attackSpeed", "Attack Speed", "text-text", ""],
  ["crit", "Crit", "text-gold", "%"],
  ["haste", "General AH", "text-accent", ""],
  ["basicAbilityHaste", "Basic Ability AH", "text-accent", ""],
  ["ultimateAbilityHaste", "Ultimate AH", "text-accent", ""],
  ["summonerSpellHaste", "Summoner Spell Haste", "text-accent", "%"],
  ["moveSpeed", "Move Speed", "text-text", ""],
  ["mana", "Mana", "text-blue-300", ""],
] as const;

const ADVANCED_STAT_ROWS = [
  ["physicalPenFlat", "Flat Armor Pen", "text-orange-300", ""],
  ["physicalPen", "Armor Pen", "text-orange-300", "%"],
  ["magicPenFlat", "Flat Magic Pen", "text-violet-300", ""],
  ["magicPen", "Magic Pen", "text-violet-300", "%"],
  ["critDamage", "Critical Damage", "text-gold", "%"],
  ["omnivamp", "Omnivamp", "text-rose-300", "%"],
  ["physicalVamp", "Physical Vamp", "text-rose-300", "%"],
  ["magicVamp", "Magic Vamp", "text-violet-300", "%"],
  ["tenacity", "Tenacity", "text-amber-300", "%"],
  ["healShieldPower", "Heal & Shield Power", "text-emerald-300", "%"],
  ["manaRegen", "Mana Regen / 5s", "text-blue-300", ""],
  ["hpRegen", "Health Regen / 5s", "text-emerald-300", ""],
  ["itemCost", "Total Item Cost", "text-gold", "g"],
] as const;

const ITEM_STAT_LABELS: Record<string, string> = {
  ad: "Attack Damage",
  ap: "Ability Power",
  hp: "Health",
  armor: "Armor",
  mr: "Magic Resist",
  attackSpeed: "Attack Speed",
  crit: "Critical Strike",
  abilityHaste: "Ability Haste",
  moveSpeed: "Move Speed",
  mana: "Mana",
  manaRegen: "Mana Regen",
  hpRegen: "Health Regen",
  physicalPen: "Armor Penetration",
  physicalPenFlat: "Flat Armor Penetration",
  magicPen: "Magic Penetration",
  magicPenFlat: "Flat Magic Penetration",
  physicalVamp: "Physical Vamp",
  magicVamp: "Magic Vamp",
  omnivamp: "Omnivamp",
  healShieldPower: "Heal & Shield Power",
  tenacity: "Tenacity",
};

const SCOPED_STAT_LABELS: Record<string, string> = {
  basicAbilityHaste: "Basic Ability Haste",
  ultimateAbilityHaste: "Ultimate Ability Haste",
  summonerSpellHaste: "Summoner Spell Haste",
};

const STAT_DESCRIPTIONS: Record<string, string> = {
  ad: "Increases basic-attack damage and abilities that scale with Attack Damage.",
  ap: "Increases abilities, healing, and shielding that scale with Ability Power.",
  hp: "Raises the maximum damage you can take before dying.",
  armor: "Reduces incoming physical damage. More armor has diminishing percentage returns.",
  mr: "Reduces incoming magic damage. More Magic Resist has diminishing percentage returns.",
  attackSpeed: "Controls how many basic attacks you can make each second.",
  crit: "Chance for eligible attacks and effects to deal critical-strike damage.",
  critDamage: "The damage multiplier applied when an eligible attack or effect critically strikes. The normal value is 175%.",
  haste: "General Ability Haste reduces the cooldown of both basic abilities and your ultimate.",
  basicAbilityHaste: "Effective haste for basic abilities, including general and basic-only haste such as Shojin.",
  ultimateAbilityHaste: "Effective haste for your ultimate, including general and ultimate-only haste.",
  summonerSpellHaste: "Reduces the cooldown of Summoner Spells such as Flash, Ignite, Heal, and Smite.",
  moveSpeed: "Controls how quickly your champion moves around the map and during fights.",
  mana: "Increases the resource available for casting mana-costing abilities.",
  physicalPenFlat: "Ignores a fixed amount of the target's Armor when dealing physical damage.",
  physicalPen: "Ignores a percentage of the target's Armor when dealing physical damage.",
  magicPenFlat: "Ignores a fixed amount of the target's Magic Resist when dealing magic damage.",
  magicPen: "Ignores a percentage of the target's Magic Resist when dealing magic damage.",
  omnivamp: "Restores Health from physical, magic, and true damage dealt.",
  physicalVamp: "Restores Health from physical damage dealt.",
  magicVamp: "Restores Health from magic damage dealt. Omnivamp contributes to both Physical and Magic Vamp.",
  tenacity: "Shortens most crowd-control effects, but not displacement or suppression.",
  healShieldPower: "Amplifies healing and shielding you apply.",
  manaRegen: "Mana restored every 5 seconds after champion growth and percentage regeneration bonuses.",
  hpRegen: "Health restored every 5 seconds after champion growth and percentage regeneration bonuses.",
  itemCost: "Combined gold cost of the selected completed items and boots.",
};

/**
 * Which form the panels are showing, shared between them.
 *
 * The stat sheet and the ability list are siblings rendered in several places,
 * and each owning its own toggle meant flipping Gnar to Mega changed his
 * abilities while his stats stayed on Mini -- two controls for one idea. A
 * store keyed by champion keeps them in step wherever they are mounted, and
 * resets on its own because a different champion is a different key.
 */
const formStore = new Map<string, number>();
const formListeners = new Set<() => void>();

function useChampionForm(name: string): [number, (side: number) => void] {
  const side = useSyncExternalStore(
    (cb) => { formListeners.add(cb); return () => { formListeners.delete(cb); }; },
    () => formStore.get(name) ?? 0,
    () => 0,
  );
  const set = useCallback((next: number) => {
    formStore.set(name, next);
    formListeners.forEach((cb) => cb());
  }, [name]);
  return [side, set];
}

export function BuildStatsPanel({
  name,
  itemSlugs,
  runeNames = [],
  level = 15,
  embedded = false,
}: {
  name: string;
  itemSlugs: string[];
  runeNames?: string[];
  level?: number;
  embedded?: boolean;
}) {
  // Two honest answers to "what are my stats?": what you are guaranteed to have
  // when a fight starts, and what the loadout is worth once everything that
  // ramps has ramped. Guaranteed stays the default because it is the one you
  // can rely on; scaled is what makes stacking items comparable to static ones.
  const [scaled, setScaled] = useState(false);
  // A transform ultimate's buff is a real stat change, but only while it is up,
  // so the sheet leaves it out of the guaranteed numbers by default and offers
  // it as its own state rather than mixing the two.
  const transform = ultTransform(name);
  const formNames = DUAL_FORM_CHAMPIONS[name];
  const [side, setSide] = useChampionForm(name);
  const ultOn = side === 1;
  const setUltOn = (on: boolean) => setSide(on ? 1 : 0);
  // A champion who transforms already has a name for the two states, so use it
  // rather than a second vocabulary: Gnar reads Mini / Mega, Aatrox Ult off / on.
  const labels = formNames ?? ["Ult off", "Ult on"];
  const base = listedBuildStats(name, [], level);
  const listed = listedBuildStats(name, itemSlugs, level, runeNames, ultOn);
  const scaledResult = scaledBuildStats(name, itemSlugs, level, runeNames, ultOn);
  if (!base || !listed) return null;
  const stats = scaled && scaledResult ? scaledResult.stats : listed;
  const contributions = scaledResult?.contributions ?? [];
  const runeEffects = scaledResult?.runeEffects ?? [];
  const scalable = scalingSources(itemSlugs, runeNames);
  const unmodelled = unmodelledRunes(runeNames);
  const conditionalEffects = conditionalBuildEffects(itemSlugs);
  const primaryRows = STAT_ROWS.filter(([key]) => stats[key] !== 0);
  const advancedRows = ADVANCED_STAT_ROWS.filter(([key]) => stats[key] !== 0);

  return (
    <div
      data-tour="build-stats"
      className={embedded ? "mt-3 border-t border-line/60 pt-3" : "glass rounded-2xl p-4"}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          Champion stats{" "}
          <span className="normal-case text-faint/60">
            · level {level} base + {scaled ? "fully scaled build stats" : "guaranteed build stats"}
            {ultOn && transform ? ` · with ${transform.label}` : ""}
          </span>
        </p>
        {transform && (
          <div className="flex items-center gap-0.5 rounded-lg border border-line bg-white/[0.03] p-0.5">
            <StatModeButton active={!ultOn} onClick={() => setUltOn(false)} title="Stats without the ultimate active.">
              {labels[0]}
            </StatModeButton>
            <StatModeButton
              active={ultOn}
              onClick={() => setUltOn(true)}
              title={`Stats while ${transform.label} is active.`}
            >
              {labels[1]}
            </StatModeButton>
          </div>
        )}
        {scalable.length > 0 && (
          <div className="flex items-center gap-0.5 rounded-lg border border-line bg-white/[0.03] p-0.5">
            <StatModeButton
              active={!scaled}
              onClick={() => setScaled(false)}
              title="Only stats you are guaranteed to have the moment a fight starts"
            >
              Guaranteed
            </StatModeButton>
            <StatModeButton
              active={scaled}
              onClick={() => setScaled(true)}
              title="Adds every stacking, ramping and converted stat at its maximum modelled value"
            >
              Fully scaled
            </StatModeButton>
          </div>
        )}
      </div>
      <div className="grid grid-cols-3 gap-x-2 gap-y-3 text-center sm:grid-cols-6">
        {primaryRows.map(([key, label, cls, suffix]) => (
          <StatDelta
            key={key}
            label={label}
            value={stats[key]}
            delta={stats[key] - base[key]}
            cls={cls}
            suffix={suffix}
            description={statDescription(key, stats[key])}
            limit={statLimit(key, stats[key], itemSlugs, runeNames)}
          />
        ))}
      </div>
      <details className="group mt-3 rounded-xl border border-line/60 bg-white/[0.025]">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-bold text-muted transition hover:text-text">
          <span>
            Advanced stats
            <span className="ml-1.5 font-normal text-faint">
              {advancedRows.length ? `${advancedRows.length} active` : "none in this build"}
            </span>
          </span>
          <span aria-hidden className="text-accent transition group-open:rotate-180">⌄</span>
        </summary>
        <div className="border-t border-line/60 p-3">
          {advancedRows.length > 0 ? (
            <div className="grid grid-cols-2 gap-x-2 gap-y-3 text-center sm:grid-cols-4 lg:grid-cols-6">
              {advancedRows.map(([key, label, cls, suffix]) => (
                <StatDelta
                  key={key}
                  label={label}
                  value={stats[key]}
                  delta={stats[key] - base[key]}
                  cls={cls}
                  suffix={suffix}
                  description={statDescription(key, stats[key])}
                  limit={statLimit(key, stats[key], itemSlugs, runeNames)}
                />
              ))}
            </div>
          ) : (
            <p className="text-center text-xs text-faint">No advanced item stats are active.</p>
          )}
          <p className="mt-3 text-center text-[0.65rem] text-faint">
            Adaptive, stacking, target-dependent, and triggered passives stay in item details and are not added here.
          </p>
        </div>
      </details>
      {scaled && contributions.length > 0 && (
        <details className="group mt-3 rounded-xl border border-accent/20 bg-accent/[0.04]" open>
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-bold text-accent">
            <span>
              What scaling added
              <span className="ml-1.5 font-normal text-faint">· {contributions.length} values on top of the guaranteed sheet</span>
            </span>
            <span aria-hidden className="transition group-open:rotate-180">⌄</span>
          </summary>
          <div className="space-y-1.5 border-t border-accent/10 p-3">
            {contributions.map((entry, index) => (
              <p key={`${entry.source}-${entry.stat}-${index}`} className="text-xs text-muted">
                <span className="font-semibold text-text">{entry.source}:</span> {entry.note}
              </p>
            ))}
            <p className="pt-1 text-[0.65rem] text-faint">
              Maximum modelled values: full stacks, full ramp, conversions resolved against this build. Real
              games rarely sit at every maximum at once.
            </p>
          </div>
        </details>
      )}
      {/* Runes that pay in damage, shields or speed rather than in stats. They
          are real and quantified, so they are shown, but folding a Dark Harvest
          proc into Attack Damage would claim a number you do not have. */}
      {scaled && runeEffects.length > 0 && (
        <details className="group mt-3 rounded-xl border border-violet-400/20 bg-violet-400/[0.04]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-bold text-violet-300">
            <span>
              Rune effects at full stacks
              <span className="ml-1.5 font-normal text-faint">· {runeEffects.length} values that are not stats</span>
            </span>
            <span aria-hidden className="transition group-open:rotate-180">⌄</span>
          </summary>
          <div className="space-y-1.5 border-t border-violet-400/10 p-3">
            {runeEffects.map((effect, index) => (
              <p key={`${effect.rune}-${effect.label}-${index}`} className="text-xs text-muted">
                <span className="font-semibold text-text">{effect.rune} · {effect.label}:</span>{" "}
                <span className="text-violet-200">{effect.value}</span>
                {effect.note ? <span className="text-faint"> · {effect.note}</span> : null}
              </p>
            ))}
            <p className="pt-1 text-[0.65rem] text-faint">
              Damage, shields and transient speed. Kept out of the stat totals on purpose.
            </p>
          </div>
        </details>
      )}
      {scaled && unmodelled.length > 0 && (
        <p className="mt-2 text-center text-[0.65rem] text-faint">
          No quantified value for {unmodelled.join(", ")}, so {unmodelled.length === 1 ? "it is" : "they are"} not counted above.
        </p>
      )}
      {scaled && contributions.length === 0 && runeEffects.length === 0 && (
        <p className="mt-3 rounded-xl border border-line/60 bg-white/[0.025] px-3 py-2 text-center text-xs text-faint">
          Nothing in this build scales: every stat it grants is already guaranteed.
        </p>
      )}
      {conditionalEffects.length > 0 && (
        <details className="group mt-3 rounded-xl border border-amber-300/15 bg-amber-300/[0.035]">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-2 text-xs font-bold text-amber-200">
            <span>Conditional combat stats <span className="font-normal text-faint">· {conditionalEffects.length} effects excluded from resting totals</span></span>
            <span aria-hidden className="transition group-open:rotate-180">⌄</span>
          </summary>
          <div className="space-y-2 border-t border-amber-300/10 p-3">
            {conditionalEffects.map((effect, index) => (
              <p key={`${effect.source}-${effect.label}-${index}`} className="text-xs text-muted">
                <span className="font-semibold text-text">{effect.source} · {effect.label}:</span> {effect.detail}
              </p>
            ))}
          </div>
        </details>
      )}
      <p className="mt-2 text-center text-[0.65rem] text-faint">
        {scaled
          ? "Stacking items, ramping passives and stat conversions are counted at their maximum. Triggered damage procs are still excluded."
          : "Unconditional scoped haste and guaranteed rune stats are included. Triggered effects are not."}
      </p>
    </div>
  );
}

function StatModeButton({
  active, onClick, title, children,
}: {
  active: boolean; onClick: () => void; title: string; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      aria-pressed={active}
      className={`rounded-md px-2.5 py-1 text-[0.65rem] font-bold transition ${
        active ? "bg-accent/20 text-accent" : "text-muted hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}


/** The half of a two-form ability that belongs to the selected form. */
function abilityForForm<T extends {
  name: string; icon: string; formIcons?: string[]; damage: any[]; effects: any[];
}>(ability: T, side: number): T {
  const halves = ability.name.split(" / ").map((part) => part.trim());
  if (halves.length !== 2) return ability;          // shared across both forms
  const mine = halves[side].toLowerCase();
  const theirs = halves[1 - side].toLowerCase();
  const pick = <P extends { label: string }>(parts: P[]): P[] => {
    const own = parts.filter((p) => p.label.toLowerCase().includes(mine));
    if (own.length) return own;
    // Attributable to the OTHER form only, so this form does not show it.
    // Anything matching neither name is kit-wide and stays visible.
    return parts.filter((p) => !p.label.toLowerCase().includes(theirs));
  };
  return {
    ...ability,
    name: halves[side],
    // The guide page has one combined image per slot, so the per-form art is
    // sourced separately; fall back to the shared icon when it is missing.
    icon: ability.formIcons?.[side] || ability.icon,
    damage: pick(ability.damage),
    effects: pick(ability.effects),
  };
}

export function ChampionAbilitiesPanel({
  name,
  itemSlugs = [],
  runeNames = [],
  level = 15,
  embedded = false,
}: {
  name: string;
  itemSlugs?: string[];
  runeNames?: string[];
  level?: number;
  embedded?: boolean;
}) {
  const formNames = DUAL_FORM_CHAMPIONS[name];
  const [formSide, setFormSide] = useChampionForm(name);
  // Ultimates that transform the champion (Aatrox's +50% AD, Shyvana's +600
  // Health) change every other number on this panel, because the buff feeds the
  // same AD/AP the ability ratios read from. The stat sheet lists only
  // unconditional stats, so without this the transformed values were nowhere.
  const transform = ultTransform(name);
  const ultOn = formSide === 1;
  const setUltOn = (on: boolean) => setFormSide(on ? 1 : 0);
  // For a champion whose FORM is the ultimate (Gnar rages, Jayce swaps weapon,
  // Yunara transcends), the form switch already says whether the ult is up, so
  // it drives the stats too rather than sitting next to a second toggle that
  // means the same thing.
  const ultActive = formNames ? formSide === 1 : ultOn;
  const raw = calculatedChampionAbilities(name, itemSlugs, runeNames, level, ultActive);
  const abilities = formNames ? raw.map((a) => abilityForForm(a, formSide)) : raw;
  if (!abilities.length) return null;

  return (
    <div data-tour="ability-values" className={embedded ? "mt-3 border-t border-line/60 pt-3" : "glass rounded-2xl p-4"}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          Live ability values <span className="normal-case text-faint/60">· level {level} with this build</span>
        </p>
        {transform && !formNames && (
          <div className="ml-auto flex gap-1 rounded-lg border border-line bg-black/30 p-0.5">
            <StatModeButton active={!ultOn} onClick={() => setUltOn(false)} title="Values without the ultimate active.">
              Ult off
            </StatModeButton>
            <StatModeButton
              active={ultOn}
              onClick={() => setUltOn(true)}
              title={`${transform.label} active: the buff it grants feeds every ratio below.`}
            >
              Ult on
            </StatModeButton>
          </div>
        )}
        {formNames && (
          <div className="ml-auto flex gap-1 rounded-lg border border-line bg-black/30 p-0.5">
            {formNames.map((label, index) => (
              <StatModeButton
                key={label}
                active={index === formSide}
                onClick={() => setFormSide(index)}
                title={`${label} Form abilities. ${name} switches freely, so both share one build.`}
              >
                {label}
              </StatModeButton>
            ))}
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {abilities.map((ability) => (
          <Tip
            key={`${ability.slot}-${ability.name}`}
            wide
            tip={
              <>
                <span className="font-bold text-text">{ability.key} · {ability.name}</span>
                <span className="ml-1 text-faint">· {ability.rank > 0 ? `rank ${ability.rank}/${ability.maxRank}` : `unlocks at level ${ability.unlockLevel ?? "?"}`}</span>
                {ability.cooldown !== undefined && (
                  <span className="mt-1 block text-accent">
                    Cooldown: {ability.baseCooldown}s → {ability.cooldown}s with {ability.hasteUsed} haste
                  </span>
                )}
                {ability.cooldownVariants.map((variant) => (
                  <span key={variant.label} className="mt-1 block text-accent">
                    {variant.label}: {variant.cooldown}s{variant.note ? ` · ${variant.note}` : ""}
                  </span>
                ))}
                {ability.damage.map((part, index) => (
                  <span key={`${part.label}-${index}`} className="mt-1.5 block text-muted">
                    <span className="font-semibold text-text">{part.label}:</span>{" "}
                    {part.amount} {part.type}
                    {part.total !== undefined && ` per hit · ${part.total} full ${part.hits > 1 ? `${part.hits}-hit ` : ""}total`}
                    {part.unresolved.length > 0 && ` + ${part.unresolved.join(" + ")}`}
                    <span className="block text-faint">{part.breakdown}{part.context ? ` · ${part.context}` : ""}</span>
                  </span>
                ))}
                {ability.effects.map((effect, index) => (
                  <span key={`${effect.label}-${index}`} className="mt-1.5 block text-muted">
                    <span className="font-semibold text-text">{effect.label}:</span> {effect.value}
                    {effect.context && <span className="block text-faint">{effect.context}</span>}
                  </span>
                ))}
                {ability.fallbackText && (
                  <span className="mt-1.5 block text-faint">No reliable fixed number is available: {ability.fallbackText}</span>
                )}
                {ability.notes.map((note, index) => (
                  <span key={index} className="mt-1.5 block text-faint">{note}</span>
                ))}
              </>
            }
          >
            <span className="flex min-h-32 w-full cursor-pointer flex-col items-center rounded-xl bg-white/[0.04] p-2 text-center transition hover:bg-white/[0.07]">
              {ability.icon && <img src={ability.icon} alt="" width={38} height={38} className="rounded-lg ring-1 ring-white/10" />}
              <span className="mt-1 text-xs font-bold text-text">{ability.key} · {ability.name}</span>
              <span className="text-[0.58rem] text-faint">{ability.rank > 0 ? `Rank ${ability.rank}/${ability.maxRank}` : `Unlocks level ${ability.unlockLevel ?? "?"}`}</span>
              {ability.rank > 0 && (
                <span className="mt-1 flex flex-col gap-0.5 text-[0.62rem] leading-tight">
                  {ability.cooldownVariants.length > 0 ? ability.cooldownVariants.map((variant) => (
                    <span key={variant.label} className="font-bold text-accent">{variant.cooldown}s {variant.label.toLowerCase()}</span>
                  )) : ability.cooldown !== undefined && <span className="font-bold text-accent">{ability.cooldown}s cooldown</span>}
                  {ability.damage.slice(0, 1).map((part) => (
                    <span key={part.label} className={damageTone(part.type)}>
                      {part.total ?? part.amount} {part.total !== undefined ? "total " : ""}{part.type}
                      {part.unresolved.length > 0 && " + target scaling"}
                    </span>
                  ))}
                  {ability.damage.length === 0 && ability.effects[0] && (
                    <span className="text-emerald-300">{ability.effects[0].value} {ability.effects[0].label.toLowerCase()}</span>
                  )}
                  {ability.damage.length === 0 && ability.effects.length === 0 && (
                    <span className="text-muted">Dynamic / conditional effect</span>
                  )}
                </span>
              )}
            </span>
          </Tip>
        ))}
      </div>
      <p className="mt-2 text-center text-[0.65rem] text-faint">
        Raw pre-mitigation values update with level, items, and guaranteed rune stats. Hover or tap for formulas; target and triggered effects remain labeled.
      </p>
    </div>
  );
}

export function ItemDetail({ item }: { item: CustomizerItem }) {
  const stats = Object.entries(item.stats).map(([key, raw]) => {
    const value = typeof raw === "number" ? raw : Number(raw.value ?? 0);
    const percent = typeof raw === "number" ? false : Boolean(raw.percent);
    return `${value > 0 ? "+" : ""}${value}${percent ? "%" : ""} ${ITEM_STAT_LABELS[key] ?? key}`;
  });
  const scopedStats = Object.entries(item.scopedStats).map(([key, raw]) => {
    const value = typeof raw === "number" ? raw : Number(raw.value ?? 0);
    const percent = typeof raw === "number" ? false : Boolean(raw.percent);
    return `${value > 0 ? "+" : ""}${value}${percent ? "%" : ""} ${SCOPED_STAT_LABELS[key] ?? key}`;
  });
  return (
    <>
      <span className="font-bold text-text">{item.name}</span>
      <span className="text-gold"> · {item.cost.toLocaleString()}g</span>
      {stats.length > 0 && <span className="mt-1 block text-accent">{stats.join(" · ")}</span>}
      {scopedStats.length > 0 && <span className="mt-1 block text-accent">{scopedStats.join(" · ")}</span>}
      {item.passives.map((passive, index) => (
        <span key={index} className="mt-1.5 block text-muted">{passive}</span>
      ))}
    </>
  );
}

export function RuneDetail({ rune }: { rune: CustomizerRune }) {
  return (
    <>
      <span className="font-bold text-text">{rune.name}</span>
      {rune.tree && <span className="text-faint"> · {rune.tree}</span>}
      {rune.description && <span className="mt-1.5 block text-muted">{rune.description}</span>}
    </>
  );
}

function damageTone(type: string): string {
  if (type.toLowerCase().includes("physical")) return "text-orange-300";
  if (type.toLowerCase().includes("magic")) return "text-violet-300";
  if (type.toLowerCase().includes("true")) return "text-text";
  return "text-muted";
}

function statDescription(key: string, value: number): string {
  const explanation = STAT_DESCRIPTIONS[key] ?? "An unconditional stat provided by the selected items.";
  if (!["haste", "basicAbilityHaste", "ultimateAbilityHaste", "summonerSpellHaste"].includes(key) || value <= 0) {
    return explanation;
  }
  const cooldownReduction = Math.round((value / (100 + value)) * 1000) / 10;
  return `${explanation} ${value} haste is approximately ${cooldownReduction}% shorter cooldowns.`;
}

type StatLimit = { badge?: string; detail: string; tone?: string };

function statLimit(key: string, value: number, itemSlugs: string[], runeNames: string[]): StatLimit {
  if (key === "crit") {
    const overflow = Math.max(0, value - 100);
    const hasInfinityEdge = itemSlugs.includes("infinity-edge");
    if (overflow > 0 && hasInfinityEdge) {
      const converted = Math.round(overflow * 0.6 * 10) / 10;
      return {
        badge: "IE converts overcap",
        tone: "text-gold",
        detail: `Critical Rate is capped at 100%. Infinity Edge converts the current ${overflow}% item overflow into +${converted}% Critical Damage; it does not raise the 100% Critical Rate cap.`,
      };
    }
    if (overflow > 0) {
      return {
        badge: `${overflow}% wasted`,
        tone: "text-bad",
        detail: `Critical Rate is capped at 100%. The current ${overflow}% overflow has no effect without an explicit overflow-conversion effect such as Infinity Edge.`,
      };
    }
    return { badge: "100% cap", tone: "text-gold", detail: "Critical Rate has a hard 100% cap. Infinity Edge can convert item Critical Rate above 100% into Critical Damage." };
  }
  if (key === "attackSpeed") {
    const hasLethalTempo = runeNames.some((name) => name.toLowerCase() === "lethal tempo");
    return {
      badge: hasLethalTempo ? "Cap breaker equipped" : "2.5 normal cap",
      tone: hasLethalTempo ? "text-emerald-300" : "text-amber-300",
      detail: hasLethalTempo
        ? "The normal Attack Speed cap is 2.5 attacks per second. Fully stacked Lethal Tempo explicitly allows you to exceed it."
        : "The normal Attack Speed cap is 2.5 attacks per second. Explicit cap-breaking effects such as fully stacked Lethal Tempo can exceed it.",
    };
  }
  if (key === "moveSpeed") {
    return {
      badge: "Soft capped",
      tone: "text-amber-300",
      detail: "Movement Speed has diminishing returns at high values rather than one universal hard cap. This sheet shows the raw listed total before temporary effects and in-game soft-cap adjustments.",
    };
  }
  if (key === "tenacity") {
    return {
      badge: "0.5s CC floor",
      tone: "text-amber-300",
      detail: "Tenacity sources can stack under Wild Rift's stacking rules, but affected crowd control cannot be reduced below 0.5 seconds. Some control types ignore Tenacity.",
    };
  }
  if (["physicalPenFlat", "physicalPen", "magicPenFlat", "magicPen"].includes(key)) {
    return { detail: "No universal hard stat cap is applied here, but penetration cannot provide further benefit once the target has no applicable resistance left. Item exclusivity rules can also prevent some combinations." };
  }
  if (key === "itemCost") {
    return { detail: "Gold has no stat cap. The practical constraints are available income, item slots, and mutually exclusive item rules." };
  }
  if (["haste", "basicAbilityHaste", "ultimateAbilityHaste", "summonerSpellHaste"].includes(key)) {
    return { detail: "Haste has no hard cap, but each additional point removes a smaller fraction of the remaining cooldown." };
  }
  return { detail: "No general hard cap is applied to this stat. Champion, item, mode, and effect-specific rules can still impose local limits." };
}

function StatDelta({
  label,
  value,
  delta,
  cls,
  suffix,
  description,
  limit,
}: {
  label: string;
  value: number;
  delta: number;
  cls: string;
  suffix: string;
  description: string;
  limit: StatLimit;
}) {
  const roundedValue = Math.round(value * 100) / 100;
  const roundedDelta = Math.round(delta * 100) / 100;
  return (
    <div className="min-w-0">
      <Tip
        wide
        tip={
          <>
            <span className="font-bold text-text">{label}</span>
            <span className="mt-1 block text-muted">{description}</span>
            <span className="mt-1.5 block border-t border-line/60 pt-1.5 text-faint">
              <span className="font-semibold text-text">Limit: </span>{limit.detail}
            </span>
          </>
        }
      >
        <button
          type="button"
          aria-label={`${label}: ${roundedValue.toLocaleString()}${suffix}. ${description} Limit: ${limit.detail}`}
          className="w-full rounded-lg px-1 py-0.5 transition hover:bg-white/[0.05] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent/70"
        >
          <span className={`block text-lg font-bold ${cls}`}>
            {roundedValue.toLocaleString()}{suffix}
            {roundedDelta !== 0 && (
              <span className={`ml-0.5 text-[0.6rem] font-semibold ${roundedDelta > 0 ? "text-emerald-300" : "text-bad"}`}>
                {roundedDelta > 0 ? "+" : ""}{roundedDelta}
              </span>
            )}
          </span>
          <span className="block text-[0.55rem] uppercase tracking-wide text-faint">{label}</span>
          {limit.badge && <span className={`mt-0.5 block text-[0.5rem] font-bold uppercase tracking-wide ${limit.tone ?? "text-faint"}`}>{limit.badge}</span>}
        </button>
      </Tip>
    </div>
  );
}
