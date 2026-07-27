"use client";

import { useState } from "react";
import Link from "next/link";
import type { AbilityCard } from "@/lib/champion-details";
import { KAYN_FORMS } from "@/lib/build-options";
import { useBuildToolsVisible } from "@/lib/use-build-tools";

/* eslint-disable @next/next/no-img-element */

type FormKey = (typeof KAYN_FORMS)[number]["key"];

const FORM_DETAILS: Record<FormKey, { bestInto: string; identity: string; build: string[]; tone: string }> = {
  "shadow-assassin": {
    bestInto: "Ranged and fragile enemy teams",
    identity: "Fast roaming assassin with explosive opening damage and superior terrain mobility.",
    build: ["Physical burst and penetration", "Mobility and target access", "Short-fight keystones"],
    tone: "border-sky-400/30 bg-sky-400/[0.06] text-sky-300",
  },
  rhaast: {
    bestInto: "Melee, bruiser, and high-Health enemy teams",
    identity: "Sustained Darkin bruiser with healing, max-Health damage, and a knock-up.",
    build: ["Ability haste and repeated casts", "Bruiser durability and healing", "Sustained-fight keystones"],
    tone: "border-red-400/30 bg-red-400/[0.06] text-red-300",
  },
};

function FormToggle({ value, onChange }: { value: FormKey; onChange: (value: FormKey) => void }) {
  return (
    <div className="grid grid-cols-2 gap-1 rounded-xl border border-line bg-white/[0.025] p-1">
      {KAYN_FORMS.map((form) => (
        <button key={form.key} type="button" onClick={() => onChange(form.key)}
          className={`rounded-lg px-3 py-2 text-sm font-semibold transition ${value === form.key ? (form.key === "rhaast" ? "bg-red-400/15 text-red-300" : "bg-sky-400/15 text-sky-300") : "text-muted hover:text-text"}`}>
          <span className="block">{form.label}</span>
          <span className="block text-[0.6rem] font-normal opacity-75">{form.shortLabel}</span>
        </button>
      ))}
    </div>
  );
}

export function KaynFormGuide() {
  const [form, setForm] = useState<FormKey>("shadow-assassin");
  const data = FORM_DETAILS[form];
  const buildToolsVisible = useBuildToolsVisible();
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-lg font-semibold">Choose Kayn&apos;s form</h2><p className="mt-1 text-sm text-muted">The form changes the kit, matchups, runes, and item priorities—not just the label.</p></div>
        {buildToolsVisible && <Link href={`/build?champion=kayn&tab=generate`} className="rounded-full bg-accent/15 px-3 py-1.5 text-xs font-semibold text-accent">Generate a form build →</Link>}
      </div>
      <div className="mt-4 max-w-lg"><FormToggle value={form} onChange={setForm} /></div>
      <div className={`mt-4 rounded-xl border p-4 ${data.tone}`}>
        <p className="text-xs font-bold uppercase tracking-wide opacity-80">Best into</p>
        <p className="mt-1 font-semibold">{data.bestInto}</p>
        <p className="mt-2 text-sm leading-relaxed text-muted">{data.identity}</p>
        <div className="mt-3 flex flex-wrap gap-1.5">{data.build.map((point) => <span key={point} className="rounded-md bg-black/15 px-2 py-1 text-xs">{point}</span>)}</div>
      </div>
    </div>
  );
}

export function KaynAbilities({ shadowAbilities, rhaastAbilities }: {
  shadowAbilities: AbilityCard[];
  /** Rhaast's real scraped kit. Both forms are on the guide page; only the
   *  first five blocks used to be parsed, so this was hand-written prose with
   *  no numbers and Shadow Assassin's icons until the scraper kept both. */
  rhaastAbilities?: AbilityCard[];
}) {
  const [form, setForm] = useState<FormKey>("shadow-assassin");
  const abilities = form === "rhaast" && rhaastAbilities?.length
    ? rhaastAbilities
    : shadowAbilities;
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><h2 className="text-lg font-semibold">Kayn abilities by form</h2><p className="mt-1 text-sm text-muted">Switch forms to see the transformed effects and cooldowns.</p></div>
        <div className="w-full sm:w-[310px]"><FormToggle value={form} onChange={setForm} /></div>
      </div>
      <div className="mt-6 space-y-5">
        {abilities.map((ability) => (
          <div key={`${form}-${ability.slot}`} className="flex gap-3.5">
            <div className="relative shrink-0">
              {ability.icon ? <img src={ability.icon} alt={ability.name} width={48} height={48} className="rounded-lg ring-1 ring-white/10" /> : <span className="grid h-12 w-12 place-items-center rounded-lg bg-white/[0.06] text-sm font-bold text-faint">{ability.key}</span>}
              <span className="absolute -left-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-[#0e1322] px-1 text-[0.6rem] font-bold text-accent ring-1 ring-line">{ability.key}</span>
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2"><span className="font-semibold">{ability.name}</span>{ability.cooldowns.length > 0 && <span className="text-[0.7rem] text-faint">CD {ability.cooldowns.join(" / ")}s</span>}</div>
              <p className="mt-1 text-sm leading-relaxed text-muted">{ability.text}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
