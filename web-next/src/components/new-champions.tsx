import { Card } from "@/components/ui";
import { getNewChampions, type NewChampion } from "@/lib/new-champions";

/* eslint-disable @next/next/no-img-element */

const SLOT_LABEL: Record<string, string> = {
  P: "Passive", "1": "1", "2": "2", "3": "3", "4": "Ultimate",
};

/**
 * Champions live in the game but not yet in our ranked dataset.
 *
 * Shown as their own section rather than mixed into the tier list, because a
 * champion with no top-50 leaderboard has no win rate we could stand behind.
 * Source attribution stays out of the UI: naming another Wild Rift site on our
 * own pages advertises them. The provenance lives in the data file and in
 * lib/new-champions.ts, where it belongs.
 */
export function NewChampions() {
  const champions = getNewChampions();
  if (champions.length === 0) return null;

  return (
    <section>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">
            Just released
            <span className="ml-2 rounded bg-emerald-400/20 px-1.5 py-0.5 align-middle text-[0.6rem] font-bold uppercase tracking-wide text-emerald-300">
              new
            </span>
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Live in Wild Rift, but not on any leaderboard we track yet. Win rates appear here as soon as
            enough ranked games exist to mean anything.
          </p>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {champions.map((champion) => (
          <NewChampionCard key={champion.slug} champion={champion} />
        ))}
      </div>
    </section>
  );
}

function NewChampionCard({ champion }: { champion: NewChampion }) {
  // A champion that is only announced has placeholder scraped stats, so we do
  // not show numbers we cannot stand behind. `comingSoon` is the single switch
  // for that: N/A stats, a "Coming soon" badge, and no abilities panel (its
  // ability text is a stub too).
  const soon = champion.comingSoon === true;
  const hp = champion.baseStats.hp;
  const ad = champion.baseStats.ad;
  const armor = champion.baseStats.armor;

  return (
    <Card className="overflow-hidden">
      <div className="relative">
        {champion.splash && (
          <>
            <img
              src={champion.splash}
              alt=""
              aria-hidden
              className={`absolute inset-0 h-full w-full object-cover object-top ${soon ? "opacity-15 grayscale" : "opacity-25"}`}
            />
            <div className="absolute inset-0 bg-gradient-to-r from-[#070a12] via-[#070a12]/85 to-transparent" />
          </>
        )}
        {/* Smaller than before: less padding, a 44px icon, tighter type. The
            row still wraps cleanly on a narrow phone. */}
        <div className="relative flex flex-wrap items-center gap-2.5 p-4">
          <span className={`h-11 w-11 shrink-0 overflow-hidden rounded-full ring-1 ring-white/10 ${soon ? "grayscale" : ""}`}>
            <img src={champion.icon} alt={`${champion.name} icon`} width={44} height={44} className="h-full w-full object-cover" />
          </span>
          <div className="min-w-0 flex-1">
            <h3 className="text-lg font-semibold">{champion.name}</h3>
            <p className="text-xs text-muted">
              {champion.role} · {champion.class}
              {!soon && champion.primaryDamage ? ` · ${champion.primaryDamage} damage` : ""}
            </p>
          </div>
          {soon ? (
            <span className="rounded-md bg-accent/15 px-2 py-1 text-[0.6rem] font-bold uppercase tracking-wide text-accent">
              Coming soon
            </span>
          ) : (
            <span className="rounded-md bg-gold/10 px-2 py-1 text-[0.6rem] font-semibold text-gold">
              Win rates pending
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 border-t border-line/60 px-4 py-2.5 text-center">
        <Stat label="Health" value={soon || !hp ? "N/A" : hp.lvl15.toLocaleString()} sub="at level 15" muted={soon} />
        <Stat label="Attack damage" value={soon || !ad ? "N/A" : String(ad.lvl15)} sub="at level 15" muted={soon} />
        <Stat label="Armor" value={soon || !armor ? "N/A" : String(armor.lvl15)} sub="at level 15" muted={soon} />
      </div>

      {!soon && champion.abilities.length > 0 && (
        <details className="group border-t border-line/60">
          <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-2.5 text-sm font-semibold">
            {champion.name}&rsquo;s abilities
            <span aria-hidden className="text-accent transition group-open:rotate-180">⌄</span>
          </summary>
          <div className="space-y-3 border-t border-line/60 px-4 py-4">
            {champion.abilities.map((ability) => (
              <div key={`${ability.slot}-${ability.name}`} className="flex gap-3">
                <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-accent/20 text-xs font-bold text-accent">
                  {SLOT_LABEL[ability.slot] === "Passive" ? "P" : ability.slot}
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">{ability.name}</p>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted">{ability.text}</p>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

      {!soon && champion.mechanics.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-line/60 px-4 py-2.5">
          {champion.mechanics.map((mechanic) => (
            <span key={mechanic} className="rounded-md bg-white/[0.06] px-2 py-0.5 text-xs text-muted">
              {mechanic}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

function Stat({ label, value, sub, muted }: { label: string; value: string; sub: string; muted?: boolean }) {
  return (
    <div>
      <p className={`text-base font-semibold ${muted ? "text-faint" : ""}`}>{value}</p>
      <p className="text-[0.6rem] font-semibold uppercase tracking-wide text-faint">{label}</p>
      <p className="text-[0.6rem] text-faint">{sub}</p>
    </div>
  );
}
