"use client";

import { useMemo } from "react";
import engineData from "@/data/engine.json";
import { threatProfile, recommendCounters } from "@/lib/threat";

/* eslint-disable @next/next/no-img-element */

/**
 * What the counter builder knows about the enemy team, shown to the player.
 *
 * Two halves, deliberately separated by WHEN they are true:
 *
 *   EnemyRead      derived on the spot from the picked enemies (lib/threat.ts,
 *                  which reads every champion's own base stats and kit tags).
 *                  It needs no generation, so it answers while the player is
 *                  still picking -- the point in a draft when it is worth most.
 *
 *   CounterReasoning  the advisor's own account of the build it returned:
 *                  which problems it chose to solve, what each item and rune
 *                  answers, what it gave up, and what no build can answer.
 *                  The generator has always produced this; nothing rendered it,
 *                  so counter mode explained itself less than any other mode
 *                  while being the mode whose reasoning matters most.
 */

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string }>;
};
const itemName = (slug: string): string => DATA.items?.[slug]?.name ?? slug;
const itemIcon = (slug: string): string | undefined => DATA.items?.[slug]?.icon;

export interface CounterSummary {
  confidence: number;
  counterPriorities: string[];
  threatResponses: { choiceType: string; choice: string; answers: string[]; reason: string }[];
  acceptedTradeoffs: string[];
  unansweredThreats: string[];
  allyContextUsed: boolean;
}

function Chip({ tone, children }: { tone: "red" | "blue" | "gold" | "muted"; children: React.ReactNode }) {
  const cls = {
    red: "bg-red-500/15 text-red-300",
    blue: "bg-accent/15 text-accent",
    gold: "bg-gold/15 text-gold",
    muted: "bg-white/[0.06] text-muted",
  }[tone];
  return (
    <span className={`rounded-md px-2 py-0.5 text-[0.7rem] font-semibold ${cls}`}>{children}</span>
  );
}

/** The damage split as one bar: the single most build-shaping fact there is. */
function DamageSplit({ ad, ap }: { ad: number; ap: number }) {
  const adPct = Math.round(ad * 100);
  const apPct = Math.max(0, 100 - adPct);
  return (
    <div>
      <div className="mb-1 flex justify-between text-[0.7rem] font-semibold">
        <span className="text-orange-300">{adPct}% physical</span>
        <span className="text-sky-300">{apPct}% magic</span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-white/[0.06]">
        <div className="bg-orange-400/70" style={{ width: `${adPct}%` }} />
        <div className="bg-sky-400/70" style={{ width: `${apPct}%` }} />
      </div>
    </div>
  );
}

/**
 * The live read on the enemy comp. Rendered from the moment one enemy is
 * named: with a single pick it describes that pick, and it sharpens as the
 * comp fills in.
 */
export function EnemyRead({ enemies, myRole }: { enemies: string[]; myRole?: string }) {
  const profile = useMemo(
    () => (enemies.length ? threatProfile(enemies, 13, myRole ?? "") : null),
    [enemies, myRole],
  );
  const recs = useMemo(() => (profile ? recommendCounters(profile) : []), [profile]);
  if (!profile) return null;

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-2 flex flex-wrap items-baseline gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          What you are up against
        </p>
        <span className="text-[0.65rem] text-faint">
          {enemies.length === 1
            ? "read on one pick; it sharpens as the comp fills in"
            : `read on ${enemies.length} picks, before any generation`}
        </span>
      </div>

      <DamageSplit ad={profile.adShare} ap={profile.apShare} />

      <div className="mt-3 flex flex-wrap gap-1.5">
        {profile.laneOpponent && (
          <Chip tone="gold">Your lane: {profile.laneOpponent}</Chip>
        )}
        {profile.healers.length > 0 && (
          <Chip tone="red">
            {profile.healers.length} sustain{profile.healers.length > 1 ? "" : ""} · {profile.healers.slice(0, 3).join(", ")}
          </Chip>
        )}
        {profile.shielders.length > 0 && (
          <Chip tone="red">{profile.shielders.length} shielding · {profile.shielders.slice(0, 3).join(", ")}</Chip>
        )}
        {profile.assassins.length > 0 && (
          <Chip tone="red">Dive threat · {profile.assassins.join(", ")}</Chip>
        )}
        {profile.marksmen.length > 0 && (
          <Chip tone="muted">{profile.marksmen.length} marksman{profile.marksmen.length > 1 ? "en" : ""}</Chip>
        )}
        {profile.ccCount > 0 && <Chip tone="muted">{profile.ccCount} with crowd control</Chip>}
      </div>

      {recs.length > 0 && (
        <div className="mt-3 border-t border-line/60 pt-3">
          <p className="mb-1.5 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
            What answers this comp
          </p>
          <ul className="space-y-1 text-xs text-muted">
            {recs.slice(0, 4).map((rec) => (
              <li key={rec.key}>
                <span className="font-semibold text-text">{rec.label}</span>
                <span className="text-faint"> — {rec.reason}</span>
              </li>
            ))}
          </ul>
          <p className="mt-1.5 text-[0.65rem] text-faint">
            The generated build weighs these against your champion rather than buying all of them.
          </p>
        </div>
      )}
    </div>
  );
}

const CHOICE_TONE: Record<string, "blue" | "gold" | "muted"> = {
  item: "blue",
  boots: "blue",
  rune: "gold",
};

/** The advisor's account of the build it just returned. */
export function CounterReasoning({ summary }: { summary: CounterSummary }) {
  const priorities = summary.counterPriorities ?? [];
  const responses = summary.threatResponses ?? [];
  const tradeoffs = summary.acceptedTradeoffs ?? [];
  const unanswered = summary.unansweredThreats ?? [];
  if (!priorities.length && !responses.length) return null;

  return (
    <div className="glass rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-baseline gap-2">
        <p className="text-[0.65rem] font-bold uppercase tracking-wide text-faint">
          Why this build, against these five
        </p>
        {typeof summary.confidence === "number" && summary.confidence > 0 && (
          <span className="text-[0.65rem] text-faint">confidence {summary.confidence}</span>
        )}
        {summary.allyContextUsed && (
          <span className="text-[0.65rem] text-faint">· your team was factored in</span>
        )}
      </div>

      {priorities.length > 0 && (
        <div className="mb-3">
          <p className="mb-1.5 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
            Problems it chose to solve
          </p>
          <div className="flex flex-wrap gap-1.5">
            {priorities.map((p) => <Chip key={p} tone="red">{p}</Chip>)}
          </div>
        </div>
      )}

      {responses.length > 0 && (
        <div className="space-y-2">
          {responses.map((r, i) => {
            const icon = itemIcon(r.choice);
            return (
              <div key={`${r.choice}-${i}`} className="flex items-start gap-2.5">
                {icon ? (
                  <img src={icon} alt="" className="mt-0.5 h-8 w-8 shrink-0 rounded-lg border border-line" />
                ) : (
                  <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-line text-[0.6rem] font-bold uppercase text-faint">
                    {r.choiceType?.slice(0, 4)}
                  </span>
                )}
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-sm font-semibold text-text">
                      {itemIcon(r.choice) ? itemName(r.choice) : r.choice}
                    </span>
                    <Chip tone={CHOICE_TONE[r.choiceType] ?? "muted"}>{r.choiceType}</Chip>
                    {(r.answers ?? []).length > 0 && (
                      <span className="text-[0.7rem] text-faint">
                        answers {r.answers.join(", ")}
                      </span>
                    )}
                  </div>
                  {r.reason && <p className="text-xs text-muted">{r.reason}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {(tradeoffs.length > 0 || unanswered.length > 0) && (
        <div className="mt-3 grid gap-3 border-t border-line/60 pt-3 sm:grid-cols-2">
          {tradeoffs.length > 0 && (
            <div>
              <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
                Accepted trade-offs
              </p>
              <ul className="space-y-0.5 text-xs text-muted">
                {tradeoffs.map((t) => <li key={t}>{t}</li>)}
              </ul>
            </div>
          )}
          {unanswered.length > 0 && (
            <div>
              <p className="mb-1 text-[0.65rem] font-bold uppercase tracking-wide text-faint">
                No build answers this
              </p>
              <ul className="space-y-0.5 text-xs text-muted">
                {unanswered.map((t) => <li key={t}>{t}</li>)}
              </ul>
              <p className="mt-1 text-[0.65rem] text-faint">Play around it instead.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
