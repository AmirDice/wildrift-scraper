import type { Metadata } from "next";
import { site, getChampions, getChampionsNa } from "@/lib/data";
import { Container, SectionHeading } from "@/components/ui";
import { LeaderboardView, type SlimChampion } from "@/components/leaderboard-view";
import items from "@/data/items.json";
import runeIcons from "@/data/rune_icons.json";
import spells from "@/data/spells.json";
import { NextStep } from "@/components/next-step";
import { PlayerQuickSearch } from "@/components/player-quick-search";
import { AdSlot } from "@/components/ad-slot";
import championSkins from "@/data/champion_skins.json";

type SkinEntry = { num: number; name: string };

// The catalogue stores the release sequence and names, while the podium only
// needs three portraits. These presentation tiers deliberately prefer clearly
// premium skin lines; if a champion has no known premium line, the newest
// available splash is used so every champion still gets a distinct portrait.
const ULTIMATE_SKINS = [
  "elementalist lux", "dj sona", "gun goddess miss fortune", "spirit guard udyr",
  "pulsefire ezreal", "k/da all out seraphine", "samurai", "soul fighter samira",
];
const LEGENDARY_SKIN_LINES = [
  "nightbringer", "dawnbringer", "spirit blossom", "star guardian", "project:",
  "battle academia", "high noon", "winterblessed", "cosmic", "dark cosmic",
  "dragonmancer", "soul fighter", "coven", "true damage", "blood moon",
];

function skinPresentationTier(name: string): "ultimate" | "legendary" | "epic" | "base" {
  const lower = name.toLowerCase();
  if (lower === "base") return "base";
  if (ULTIMATE_SKINS.some((term) => lower.includes(term))) return "ultimate";
  if (LEGENDARY_SKIN_LINES.some((term) => lower.includes(term))) return "legendary";
  return "epic";
}

function podiumSkinPortraits(slug: string) {
  const entry = (championSkins as Record<string, { key: string; skins: SkinEntry[] }>)[slug];
  if (!entry?.skins?.length) return undefined;
  // DDragon lists chroma variants as separate entries, but they do not have
  // their own splash files. Use the parent skin only so a portrait never
  // falls back to a broken *_42.jpg URL for a colour variant.
  const nonBase = entry.skins.filter((skin) =>
    skin.num !== 0 && skin.name.toLowerCase() !== "base" && !skin.name.includes("(")
  );
  // CommunityDragon's splash tiles are deliberately face-forward crops. They
  // survive the circular podium mask much better than a full splash, where a
  // champion's head can land outside the crop (or a long base splash can cover
  // the player name). Base portraits stay local so a missing PBE tile can
  // never take the whole champion card down.
  const faceShot = (skinNum: number) => {
    const key = entry.key.toLowerCase();
    const folder = skinNum < 10 ? `skin0${skinNum}` : `skin${skinNum}`;
    return `https://raw.communitydragon.org/pbe/plugins/rcp-be-lol-game-data/global/default/assets/characters/${key}/skins/${folder}/images/${key}_splash_tile_${skinNum}.jpg`;
  };
  // The existing local catalogue has one historical filename typo for Nunu;
  // keep that alias here so its base portrait is still local and reliable.
  const localSlug = slug === "nunu-and-willump" ? "nunu-amp-willump" : slug;
  const basePortrait = `/champions/${localSlug}.png`;
  if (!nonBase.length) return [{ rank: 3, name: "Base", tier: "base", url: basePortrait }];
  const tiered = (tier: "ultimate" | "legendary" | "epic") =>
    nonBase.filter((skin) => skinPresentationTier(skin.name) === tier);
  const premium = [...tiered("ultimate"), ...tiered("legendary")];
  const rankOne = premium[premium.length - 1] ?? nonBase[nonBase.length - 1];
  const epic = tiered("epic");
  const rankTwo = [...epic].reverse().find((skin) => skin.num !== rankOne.num)
    ?? [...nonBase].reverse().find((skin) => skin.num !== rankOne.num)
    ?? rankOne;
  const splashUrl = (skin: SkinEntry) => faceShot(skin.num);
  const fullSplash = (skin: SkinEntry) =>
    `https://ddragon.leagueoflegends.com/cdn/img/champion/splash/${entry.key}_${skin.num}.jpg`;
  return [
    { rank: 1, name: rankOne.name, tier: skinPresentationTier(rankOne.name), url: splashUrl(rankOne), fallback: fullSplash(rankOne) },
    { rank: 2, name: rankTwo.name, tier: skinPresentationTier(rankTwo.name), url: splashUrl(rankTwo), fallback: fullSplash(rankTwo) },
    { rank: 3, name: "Base", tier: "base", url: basePortrait },
  ];
}

// This is the page the site genuinely ranks for: "wild rift leaderboard" sits
// around position 6-8 and "wild rift leaderboard eu" around 3, where the head
// terms (tier list, meta) are stuck in the forties. The singular "Leaderboard"
// and the explicit EU qualifier both match how people actually search for it.
export const metadata: Metadata = {
  title: "Wild Rift Leaderboards | Best Players Across EU, NA and CN",
  description:
    "Wild Rift champion leaderboards with current-season top-three podiums across EU, NA and CN, plus win rate, games played, Champion Score and mastery.",
  alternates: { canonical: "/leaderboard" },
  openGraph: {
    title: "Wild Rift Leaderboards | Best Players Across EU, NA and CN",
    description:
      "Current-season champion podiums and full player tables for Wild Rift EU, NA and CN.",
    url: "https://wrtruemeta.com/leaderboard",
  },
};

export default function LeaderboardPage() {
  const champions = getChampions();
  const championsNa = getChampionsNa();
  // slug -> icon path, for the per-player build columns; slim on purpose so
  // the client bundle carries paths, not the whole item catalog
  const itemIcons: Record<string, string> = {};
  for (const it of items as { slug: string; icon?: string }[]) {
    if (it.icon) itemIcons[it.slug] = it.icon;
  }
  const toSlim = (list: typeof champions): SlimChampion[] => list.map((c) => ({
    name: c.name,
    slug: c.slug,
    icon: c.icon,
    splash: c.splash,
    role: c.role,
    class: c.class,
    tier: c.tier,
    wr: c.wr,
    isHard: c.isHard,
    bestPlayer: c.bestPlayer,
    bestPlayerPodium: c.bestPlayerPodium,
    globalBestPlayerPodium: c.globalBestPlayerPodium,
    podiumSkins: podiumSkinPortraits(c.slug),
  }));
  const slim = toSlim(champions);
  // NA's champion list is its OWN: collection is still running, so offering
  // EU's list here would show champions NA has no board for and render an
  // empty table that looks like a bug.
  const slimNa = toSlim(championsNa);

  return (
    <Container className="py-12">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">Leaderboards</h1>
      <p className="mt-2 max-w-2xl text-muted">
        See the current-season top three on every champion, then inspect the full player table
        and sort by win rate, games, mastery or confidence.
        {site.collectedOn && (
          <span className="text-faint"> Data collected {site.collectedOn}.</span>
        )}
      </p>
      {/* Looking for a person rather than a champion. Sits above the board
          because someone who arrived with a name in mind should not have to
          scan a champion table first. */}
      <section className="mt-8 sm:max-w-sm">
        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Looking for a player?
        </p>
        <PlayerQuickSearch />
      </section>

      {/* Above the player table rather than after it: the layout's bottom unit already sits after it. */}
      <AdSlot placement="inline" bare className="my-6" />
      <section id="players" className="mt-8 scroll-mt-24">
        <SectionHeading title="Champion player leaderboard" subtitle="Choose a champion and inspect its full player table, with builds, ranked tiers and per-queue stats where freshly captured" />
        <LeaderboardView
          champions={slim}
          championsNa={slimNa}
          itemIcons={itemIcons}
          runeIcons={runeIcons as Record<string, string>}
          spellIcons={Object.fromEntries(
            (spells as { name: string; icon: string }[]).map((s) => [s.name, s.icon])
          )}
        />
      </section>
      <NextStep steps={["player", "build", "meta"]} />

    </Container>
  );
}
