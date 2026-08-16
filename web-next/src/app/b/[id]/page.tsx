import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { kvGetJson } from "@/lib/kv";
import { getChampion } from "@/lib/data";
import { Container } from "@/components/ui";
import type { SharedBuild } from "@/app/api/share-build/route";
import engineData from "@/data/engine.json";

/* eslint-disable @next/next/no-img-element */

// A permanent page for one generated build, made to be dropped into Reddit,
// Discord and group chats. Server-rendered so the link unfurls with the
// champion's name and splash rather than a generic site card, which is the
// difference between a link that gets clicked and one that gets scrolled past.

const DATA = engineData as {
  items?: Record<string, { name?: string; icon?: string }>;
  runes?: Record<string, { icon?: string }>;
};
const itemIcon = (slug: string) => DATA.items?.[slug]?.icon ?? `/items/${slug}.webp`;
const itemName = (slug: string) => DATA.items?.[slug]?.name ?? slug;

const BIAS_LABEL: Record<string, string> = {
  max_durability: "Maximum Durability",
  durability: "Durability Leaning",
  damage: "Damage Leaning",
  max_damage: "Maximum Damage",
};

async function load(id: string): Promise<SharedBuild | null> {
  if (!/^[A-Za-z0-9_-]{8,16}$/.test(id)) return null;
  return kvGetJson<SharedBuild | null>(`share:build:${id}`, null);
}

export async function generateMetadata(props: PageProps<"/b/[id]">): Promise<Metadata> {
  const { id } = await props.params;
  const build = await load(id);
  if (!build) return { title: "Build not found" };
  const champ = getChampion(build.championSlug);
  const title = `${build.champion} build${build.playstyle ? ` · ${build.playstyle}` : ""}`;
  const description = `${build.items.map(itemName).join(", ")} — generated on WrTrueMeta${build.patch ? ` (patch ${build.patch})` : ""}.`;
  return {
    title,
    description,
    robots: { index: false, follow: true },
    // The build card itself, not the bare splash: the unfurl shows the items.
    openGraph: { title, description, images: [`/api/build-card?id=${id}`] },
    twitter: { card: "summary_large_image", title, description, images: [`/api/build-card?id=${id}`] },
  };
}

export default async function SharedBuildPage(props: PageProps<"/b/[id]">) {
  const { id } = await props.params;
  const build = await load(id);
  if (!build) notFound();
  const champ = getChampion(build.championSlug);
  const saved = new Date(build.createdAt);
  const savedOn = Number.isNaN(saved.getTime())
    ? null
    : saved.toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" });

  return (
    <Container className="py-10">
      <div className="glass relative mx-auto max-w-2xl overflow-hidden rounded-3xl">
        {champ?.splash && (
          <div aria-hidden className="absolute inset-0 -z-10">
            <img src={champ.splash} alt="" className="h-full w-full object-cover opacity-25" />
            <div className="absolute inset-0 bg-gradient-to-b from-transparent via-bg/60 to-bg/90" />
          </div>
        )}
        <div className="p-6 sm:p-8">
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-accent">
            WRTRUE<span className="text-text">META</span>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-4">
            {champ?.icon && (
              <img src={champ.icon} alt="" width={64} height={64}
                   className="rounded-2xl ring-2 ring-accent/40" />
            )}
            <div>
              <h1 className="text-3xl font-black tracking-tight">{build.champion}</h1>
              <p className="mt-0.5 flex flex-wrap gap-2 text-xs font-semibold text-muted">
                {build.role && <span>{build.role}</span>}
                {build.playstyle && <span className="rounded bg-accent/15 px-1.5 py-0.5 text-accent">{build.playstyle}</span>}
                {build.bias && BIAS_LABEL[build.bias] && (
                  <span className="rounded bg-gold/15 px-1.5 py-0.5 text-gold">{BIAS_LABEL[build.bias]}</span>
                )}
                {build.patch && <span>patch {build.patch}</span>}
              </p>
            </div>
          </div>

          <p className="mt-5 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Items, in order</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {build.boots && (
              <img src={itemIcon(build.boots)} alt={itemName(build.boots)} title={itemName(build.boots)}
                   width={40} height={40} className="rounded-lg ring-1 ring-white/15" />
            )}
            {build.items.map((slugName, i) => (
              <span key={`${slugName}-${i}`} className="relative">
                <img src={itemIcon(slugName)} alt={itemName(slugName)} title={itemName(slugName)}
                     width={48} height={48} className="rounded-lg ring-1 ring-white/15" />
                <span className="absolute -left-1.5 -top-1.5 grid h-[18px] w-[18px] place-items-center rounded-full bg-[#0e1322] text-[0.6rem] font-bold text-accent ring-1 ring-line">{i + 1}</span>
              </span>
            ))}
            {build.bootsUpgrade && (
              <img src={itemIcon(build.bootsUpgrade)} alt={itemName(build.bootsUpgrade)} title={itemName(build.bootsUpgrade)}
                   width={40} height={40} className="rounded-lg ring-1 ring-gold/40" />
            )}
          </div>

          {(build.summoners?.length ?? 0) > 0 && (
            <>
              <p className="mt-4 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Summoner spells</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {build.summoners!.map((spell) => (
                  <span key={spell} className="rounded-lg border border-line bg-white/[0.04] px-2.5 py-1 text-xs font-medium">
                    {spell}
                  </span>
                ))}
              </div>
            </>
          )}

          {build.runes.length > 0 && (
            <>
              <p className="mt-4 text-[0.65rem] font-bold uppercase tracking-wide text-faint">Runes</p>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                {build.runes.map((rune) => (
                  <span key={rune} className="rounded-lg border border-line bg-white/[0.04] px-2.5 py-1 text-xs font-medium">
                    {rune}
                  </span>
                ))}
              </div>
            </>
          )}

          <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-line/60 pt-4">
            <p className="text-xs text-faint">
              {build.player ? <>Built by <span className="font-bold text-text">{build.player}</span> · </> : null}
              Generated on WrTrueMeta{savedOn ? ` · ${savedOn}` : ""}
            </p>
            <Link
              href={`/build?champion=${build.championSlug}`}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-bold text-black transition hover:opacity-90"
            >
              Generate your own →
            </Link>
          </div>
        </div>
      </div>
    </Container>
  );
}
