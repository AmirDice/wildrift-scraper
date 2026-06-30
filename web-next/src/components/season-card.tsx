"use client";

import { useEffect, useState } from "react";

// --- Edit these each patch/season ---------------------------------------
const SEASON_NUM = "21";
const SEASON_TITLE = "FLAT OUT PATCH";
const SEASON_START = new Date("2026-04-22T00:00:00Z");
const SEASON_END = new Date("2026-07-09T00:00:00Z");
const NEW_CHAMPION = { name: "Skarner", icon: "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion/Skarner.png" };
const NEW_SKIN = { name: "Ashen Knight Samira", img: "/ashensamira.png" };
// ------------------------------------------------------------------------

const WARM = "#4f8dff";

export function SeasonCard() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => setNow(new Date()), []);

  const total = SEASON_END.getTime() - SEASON_START.getTime();
  const elapsed = now ? now.getTime() - SEASON_START.getTime() : 0;
  const pct = now ? Math.min(100, Math.max(0, (elapsed / total) * 100)) : 0;
  const daysLeft = now
    ? Math.max(0, Math.ceil((SEASON_END.getTime() - now.getTime()) / 86_400_000))
    : null;
  const endsAt = SEASON_END.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-line"
      style={{
        background:
          "radial-gradient(45% 130% at 0% 110%, rgba(79,141,255,0.14), transparent 60%), linear-gradient(110deg, #11131d, #0b0e16)",
      }}
    >
      <div className="grid gap-6 p-6 sm:grid-cols-[1fr_auto] sm:items-center sm:p-7">
        {/* Left — season progress */}
        <div>
          <div className="flex items-center gap-2 text-[0.7rem] font-bold uppercase tracking-[0.18em]" style={{ color: WARM }}>
            <span className="h-2 w-2 rounded-full" style={{ background: WARM, boxShadow: `0 0 8px ${WARM}` }} />
            Season in progress
          </div>
          <div className="mt-3 flex items-baseline gap-3">
            <span className="text-5xl font-black leading-none" style={{ color: WARM }}>{SEASON_NUM}</span>
            <span className="text-xl font-semibold tracking-tight">{SEASON_TITLE}</span>
          </div>
          <div className="mt-4 h-1.5 w-full max-w-lg overflow-hidden rounded-full bg-white/[0.08]">
            <div className="h-full rounded-full" style={{ width: `${pct}%`, background: `linear-gradient(90deg, ${WARM}, #8fb8ff)` }} />
          </div>
          <p className="mt-2.5 text-xs text-muted">
            <strong className="text-text">{daysLeft ?? "—"}</strong> days left
            <span className="mx-2 text-faint">·</span>ends {endsAt}
            <span className="mx-2 text-faint">·</span>{pct.toFixed(0)}% complete
          </p>
        </div>

        {/* Right — new champion + skin */}
        <div className="flex flex-col gap-2.5">
          <FeatureRow label="New champion" badge="#4f8dff" img={NEW_CHAMPION.icon} name={NEW_CHAMPION.name} round />
          <FeatureRow label="New skin" badge="#eef2fb" img={NEW_SKIN.img} name={NEW_SKIN.name} />
        </div>
      </div>
    </div>
  );
}

function FeatureRow({ label, badge, img, name, round = false }: { label: string; badge: string; img: string; name: string; round?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="shrink-0 rounded-md px-2 py-1 text-[0.6rem] font-bold uppercase tracking-wide text-[#0b0e16]"
        style={{ background: badge }}
      >
        {label}
      </span>
      <span className="flex items-center gap-2 rounded-full border border-line bg-white/[0.05] py-1 pl-1 pr-3.5">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={img}
          alt=""
          width={26}
          height={26}
          loading="lazy"
          className={`h-[26px] w-[26px] object-cover ring-1 ring-white/10 ${round ? "rounded-full" : "rounded-md"}`}
        />
        <span className="whitespace-nowrap text-sm font-semibold">{name}</span>
      </span>
    </div>
  );
}
