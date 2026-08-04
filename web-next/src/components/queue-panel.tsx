import type { QueueStats } from "@/lib/player-index";

/* One queue's performance for one player on one champion.
 *
 * Shared by the leaderboard's expanded row and the player profile so the same
 * numbers are always laid out the same way -- Ranked and Legendary Ranked are
 * different queues and comparing them only works if they read identically.
 */

export function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[0.6rem] uppercase tracking-wide text-faint">{label}</p>
      <p className="text-sm font-medium tabular-nums">{value}</p>
    </div>
  );
}

export function QueuePanel({ title, s }: { title: string; s: QueueStats }) {
  const fmt = (v: number | null, suffix = "") => (v == null ? "-" : `${v.toLocaleString()}${suffix}`);
  return (
    <div className="rounded-xl border border-line/70 bg-black/20 p-3">
      <p className="mb-2 text-xs font-semibold text-muted">{title}</p>
      <div className="grid grid-cols-3 gap-x-4 gap-y-2 sm:grid-cols-5">
        <StatCell label="Games" value={fmt(s.games)} />
        <StatCell label="Win rate" value={s.wr == null ? "-" : `${s.wr.toFixed(1)}%`} />
        <StatCell label="KDA" value={fmt(s.kda)} />
        <StatCell label="Teamfight" value={s.tf == null ? "-" : `${s.tf.toFixed(1)}%`} />
        <StatCell label="Gold/min" value={fmt(s.gpm)} />
        <StatCell label="Dmg dealt" value={fmt(s.dmg)} />
        <StatCell label="Dmg taken" value={fmt(s.taken)} />
        <StatCell label="MVPs" value={fmt(s.mvp)} />
        <StatCell label="S ratings" value={fmt(s.sRating)} />
        <StatCell label="Multikills" value={fmt((s.penta ?? 0) + (s.quadra ?? 0) + (s.triple ?? 0))} />
      </div>
    </div>
  );
}
