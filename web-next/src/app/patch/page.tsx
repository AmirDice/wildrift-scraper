import type { Metadata } from "next";
import { getChampion } from "@/lib/data";

/* eslint-disable @next/next/no-img-element */

// Temporary Patch 7.2 slide deck (for Reddit screenshots). Not in nav/sitemap.
// Full-screen scroll-snap slides: every section is exactly one viewport, so each
// scroll position is one clean screenshot. Uses the site's ambient background.
export const metadata: Metadata = {
  title: "Patch 7.2 Breakdown | WrTrueMeta",
  robots: { index: false, follow: false },
};

const DD = "https://ddragon.leagueoflegends.com/cdn/16.11.1/img/champion";
const icon = (slug: string, ddKey?: string) =>
  getChampion(slug)?.icon ?? `${DD}/${ddKey ?? slug}.png`;

// Asset fallback URL helper for item icons
const itemIcon = (id: string | number) => `https://ddragon.leagueoflegends.com/cdn/14.15.1/img/item/${id}.png`;

// ---------------------------------------------------------------- content --

const HEADLINES = [
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/champion/loading/Yunara_0.jpg", title: "Yunara arrives", sub: "New marksman · July 9", accent: "#4f8dff" },
  { glyph: "swap", title: "Actives reworked", sub: "Enchants gone · actives now class-locked items", accent: "#a78bfa" },
  { glyph: "up", title: "Tier 3 boots", sub: "Boots upgrade again at 10:00", accent: "#4ade80" },
  { glyph: "zap", title: "Mage overhaul", sub: "Deathcap 130 AP · new pen items", accent: "#7fd1ff" },
  { glyph: "crown", title: "Season 22", sub: "Ranked Energy replaces Fortitude", accent: "#ffd76e" },
  { glyph: "coin", title: "Bounty rework", sub: "Gold lead decides shutdowns", accent: "#fb7185" },
];

type Champ = { slug: string; ddKey?: string; name: string; line: string };

const BUFFED: Champ[] = [
  { slug: "kaisa", ddKey: "Kaisa", name: "Kai'Sa", line: "Ult range 4 → 5.5" },
  { slug: "kayn", name: "Kayn", line: "Ult exits further, less lockout" },
  { slug: "darius", name: "Darius", line: "W kills refund CD + mana" },
];
const NERFED: Champ[] = [
  { slug: "norra", name: "Norra", line: "Banish 2.25s → 1.5s" },
  { slug: "zed", name: "Zed", line: "Ult CD up, return locked 0.5s" },
];
const ADJUSTED: Champ[] = [
  { slug: "yasuo", name: "Yasuo", line: "Wall 22-16s, shield up" },
  { slug: "lee-sin", name: "Lee Sin", line: "E gutted, ult nukes" },
  { slug: "ksante", ddKey: "KSante", name: "K'Sante", line: "Pen is bonus-armor only" },
  { slug: "varus", name: "Varus", line: "Ult blight window halved" },
  { slug: "syndra", name: "Syndra", line: "E knockback range up" },
  { slug: "orianna", name: "Orianna", line: "Ult range 3 → 3.25" },
  { slug: "fiddlesticks", name: "Fiddlesticks", line: "Fear bug fixed" },
  { slug: "zyra", name: "Zyra + Annie", line: "Pets inherit magic pen" },
];

const CLASS_ACTIVES = [
  { 
    cls: "Mage", 
    accent: "#7fd1ff", 
    items: [
      { name: "Zhonya's Hourglass", iconUrl: "https://leagueofitems.com/images/items/256/3157.webp" },
      { name: "Seeker's Armguard", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Seeker%27s_Armguard_item.png" },
      { name: "Hextech Rocketbelt", iconUrl: "https://leagueofitems.com/images/items/256/3152.webp" }
    ] 
  },
  { 
    cls: "Fighter", 
    accent: "#fb7185", 
    items: [
      { name: "Stridebreaker", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Stridebreaker_item.png" },
      { name: "Goredrinker", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Goredrinker_item.png" }
    ] 
  },
  { 
    cls: "Marksman", 
    accent: "#ffd76e", 
    items: [
      { name: "Galeforce", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Galeforce_item.png" },
      { name: "Quicksilver Sash", iconUrl: "https://static.wikia.nocookie.net/leagueoflegends/images/a/a8/Quicksilver_Sash_item_HD.png/revision/latest?cb=20201111000632" },
      { name: "Mercurial Scimitar", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Mercurial_Scimitar_item.png" }
    ] 
  },
  { 
    cls: "Tank", 
    accent: "#4ade80", 
    items: [
      { name: "Gargoyle Stoneplate", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Gargoyle_Stoneplate_TFT_item.png?9530f" },
      { name: "Locket of the Iron Solari", iconUrl: "https://leagueofitems.com/images/items/256/3190.webp" }
    ] 
  },
  { 
    cls: "Enchanter", 
    accent: "#a78bfa", 
    items: [
      { name: "Redemption", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Redemption_WR_item.png" },
      { name: "Shurelya's Battlesong", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Shurelya%27s_Reverie_item.png" },
      { name: "Mikael's Blessing", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Mikael%27s_Blessing_item.png" }
    ] 
  },
];

const REMOVED = ["Crown of Shattered Queen", "Awakened Soulstealer", "Psychic Projector", "Dream Maker", "Prophet's Pendant", "Bandle Fantasy", "Sapphire Crystal"];

const T3_BOOTS = [
  { name: "Armored Advance", from: "Steelcaps", note: "35 armor + physical shield", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Plated_Steelcaps_item.png" },
  { name: "Chainlaced Crushers", from: "Mercs", note: "30% tenacity + magic shield", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Mercury%27s_Treads_item.png" },
  { name: "Gunmetal Greaves", from: "Berserker's", note: "50% AS, heal on hit", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Berserker%27s_Greaves_item.png" },
  { name: "Armorcrusher Boots", from: "Dynamism", note: "25 AD, armor pen", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Boots_of_Dynamism_WR_item.png" },
  { name: "Spellslinger's Shoes", from: "Boots of Mana", note: "40 AP, magic pen", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Boots_of_Mana_WR_item.png" },
  { name: "Crimson Lucidity", from: "Lucidity", note: "25 haste, MS on damage", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Ionian_Boots_of_Lucidity_item.png" },
  { name: "Immortal Treads", from: "Gluttonous", note: "Omnivamp + execute damage", iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Gluttonous_Greaves_item.png" },
];

const MAGE_ROWS = [
  { id: "3089", name: "Rabadon's Deathcap", change: "100 → 130 AP", dir: "buff" },
  { iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Infinity_Orb_WR_item_HD.png?efc5b", name: "Infinity Orb", change: "80 → 110 AP", dir: "buff" },
  { iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Luden%27s_Echo_WR_item.png?d1aec", name: "Luden's Echo", change: "85 → 100 AP, flat 10s echo", dir: "buff" },
  { id: "3100", name: "Lich Bane", change: "80 → 100 AP", dir: "buff" },
  { id: "4633", name: "Riftmaker", change: "150 → 350 HP + omnivamp", dir: "buff" },
  { iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Rod_of_Ages_WR_item.png?9e13b", name: "Rod of Ages", change: "Cheaper, much tankier", dir: "buff" },
  { id: "3135", name: "Void Staff", change: "95 AP · 40% pen rate", dir: "new" },
  { iconUrl: "https://leagueofitems.com/images/items/256/3137.webp", name: "Cryptbloom", change: "30% pen rate + AoE heal", dir: "new" },
  { iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Stormsurge_WR_item.png?ed5e8", name: "Stormsurge", change: "90 AP burst proc + MS", dir: "new" },
  { iconUrl: "https://leagueofitems.com/images/items/256/2503.webp", name: "Blackfire Torch", change: "80 AP burn, stacks per target", dir: "new" },
  { iconUrl: "https://leagueofitems.com/images/items/256/2510.webp", name: "Dusk and Dawn", change: "AP spellblade + HP + AS", dir: "new" },
];

const ITEM_ROWS = [
  { iconUrl: "https://wiki.leagueoflegends.com/en-us/images/Serylda%27s_Grudge_WR_item.png?3bcad", name: "Serylda's Grudge", change: "Slow-proc damage gutted", dir: "nerf" },
  { id: "3068", name: "Sunfire Aegis", change: "11% → 5% per stack", dir: "nerf" },
  { id: "3075", name: "Thornmail", change: "Thorns ratio halved", dir: "nerf" },
  { id: "3153", name: "Blade of the Ruined King", change: "25 → 40 AD, ranged % down", dir: "adjust" },
  { id: "3508", name: "Essence Reaver", change: "Spellblade 90% → 70%", dir: "adjust" },
  { id: "3026", name: "Guardian Angel", change: "Cheaper, full mana, 180s CD", dir: "buff" },
  { id: "3053", name: "Sterak's / Maw / Mantle", change: "Lifeline CD 90s → 75s", dir: "buff" },
  { id: "3070", name: "Tear of the Goddess", change: "Now a 500g basic item", dir: "adjust" },
];

const RUNE_ROWS = [
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Domination/Electrocute/Electrocute.png", name: "Electrocute", change: "Ratios 35/20% → 10/5%", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Precision/Conqueror/Conqueror.png", name: "Conqueror", change: "Stacks give less AD/AP", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Precision/FleetFootwork/FleetFootwork.png", name: "Fleet Footwork", change: "AS proc 100% → 40%", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Inspiration/FirstStrike/FirstStrike.png", name: "First Strike", change: "Gold gain nearly halved", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Sorcery/SummonAery/SummonAery.png", name: "Aery", change: "Ratios roughly halved", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Sorcery/ArcaneComet/ArcaneComet.png", name: "Arcane Comet", change: "Ratios 35/20% → 10/5%", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Sorcery/PhaseRush/PhaseRush.png", name: "Phase Rush", change: "Ranged MS down", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Resolve/BonePlating/BonePlating.png", name: "Bone Plating", change: "CD 30s → 40s", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Resolve/SecondWind/SecondWind.png", name: "Second Wind", change: "Heal halved", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Resolve/Overgrowth/Overgrowth.png", name: "Overgrowth", change: "Stacks 3x slower in jungle", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Domination/SuddenImpact/SuddenImpact.png", name: "Sudden Impact", change: "Late bonuses 10/20 → 5/5", dir: "nerf" },
  { iconUrl: "https://ddragon.leagueoflegends.com/cdn/img/perk-images/Styles/Resolve/GraspOfTheUndying/GraspOfTheUndying.png", name: "Grasp of the Undying", change: "More damage, half the heal", dir: "adjust" },
];

const SYSTEMS = [
  { glyph: "coin", title: "Gold-based bounties", body: "Shutdowns track gold lead. Losing teams stop feeding bounties." },
  { glyph: "up", title: "Faster games", body: "Turrets, minions and plants all spike ~1:00 earlier." },
  { glyph: "crown", title: "Ranked Energy", body: "Earned by performance. Violations now cost energy." },
  { glyph: "swap", title: "Knockdown CC", body: "New CC type that interrupts dashes (Ahri, Veigar, Jinx...)." },
  { glyph: "zap", title: "True damage amps", body: "Damage amps and reductions now affect true damage." },
  { glyph: "star", title: "Ahri visual update", body: "Rebuilt model + the map becomes Summer Rift." },
];

// ------------------------------------------------------------------- page --

export default function PatchPage() {
  const slides = 8;
  return (
    <div className="fixed inset-0 z-[100] snap-y snap-mandatory overflow-y-auto">
      {/* Site ambient background (same treatment as the layout) */}
      <div aria-hidden className="fixed inset-0 -z-20 bg-cover bg-center" style={{ backgroundImage: "url(/ionia.jpg)" }} />
      <div
        aria-hidden
        className="fixed inset-0 -z-10"
        style={{ background: "linear-gradient(180deg, rgba(7,10,18,0.84), rgba(7,10,18,0.94)), radial-gradient(70% 55% at 50% 0%, rgba(79,141,255,0.12), transparent 70%)" }}
      />

      {/* 1 · Cover + headlines */}
      <Slide n={1} of={slides}>
        <div className="text-center">
          <img src="/logo.png" alt="WrTrueMeta" className="mx-auto" style={{ height: 44, width: "auto" }} />
          <p className="mt-6 text-xs font-bold uppercase tracking-[0.3em] text-accent">Wild Rift · July 9, 2026</p>
          <h1 className="mt-3 text-5xl font-black tracking-tight sm:text-6xl">
            Patch <span className="text-accent">7.2</span> in 8 slides
          </h1>
          <p className="mt-3 text-muted">The biggest systems patch in a long time, no reading required.</p>
        </div>
        <div className="mx-auto mt-9 grid w-full max-w-4xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {HEADLINES.map((h) => (
            <div key={h.title} className="glass rounded-2xl p-4">
              <div className="flex items-center gap-3">
                {h.iconUrl ? (
                  /* Render custom champion image URL cropped perfectly */
                  <span className="h-9 w-9 shrink-0 overflow-hidden rounded-full ring-1 ring-white/15">
                    <img
                      src={h.iconUrl}
                      alt=""
                      className="h-full w-full scale-[1.2] object-cover object-top"
                    />
                  </span>
                ) : (
                  /* Fallback to standard glyph */
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl" style={{ background: `${h.accent}22`, color: h.accent }}>
                    {h.glyph && <Glyph name={h.glyph} />}
                  </span>
                )}
                <div className="min-w-0">
                  <p className="font-bold leading-tight">{h.title}</p>
                  <p className="mt-0.5 text-xs text-muted">{h.sub}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Slide>

      {/* 2 · Champions */}
      <Slide n={2} of={slides} title="Champion changes" sub="One line each, that's all you need">
        <div className="mx-auto grid w-full max-w-4xl gap-3 sm:grid-cols-2">
          <ChampCard title="Buffed" color="#4ade80" champs={BUFFED} />
          <ChampCard title="Nerfed" color="#fb7185" champs={NERFED} />
        </div>
        <div className="mx-auto mt-3 w-full max-w-4xl">
          <ChampCard title="Adjusted" color="#7fd1ff" champs={ADJUSTED} grid />
        </div>
      </Slide>

      {/* 3 · Actives */}
      <Slide n={3} of={slides} title="Actives are class-locked now" sub="Enchants are gone. Every class gets its own active items">
        <div className="mx-auto w-full max-w-3xl space-y-2.5">
          {CLASS_ACTIVES.map((r) => (
            <div key={r.cls} className="glass flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3">
              <span className="w-24 shrink-0 text-base font-black" style={{ color: r.accent }}>{r.cls}</span>
              <div className="flex flex-wrap flex-1 gap-2">
                {r.items.map((it) => (
                  <span key={it.name} className="flex items-center gap-1.5 rounded-full border border-line bg-white/[0.05] pl-1 pr-3 py-1 text-xs font-semibold">
                    <img src={it.iconUrl} alt="" className="h-5 w-5 rounded-full border border-white/10 bg-neutral-900 object-cover" />
                    {it.name}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
        <div className="mx-auto mt-5 w-full max-w-3xl rounded-2xl border border-rose-400/25 bg-rose-400/[0.07] px-4 py-3 text-center">
          <span className="text-xs font-bold uppercase tracking-wide text-rose-300">Removed</span>
          <p className="mt-1 text-sm text-muted">{REMOVED.join(" · ")}</p>
        </div>
      </Slide>

      {/* 4 · Boots */}
      <Slide n={4} of={slides} title="Tier 3 boots" sub="From 10:00 your boots upgrade again, ~2200g">
        <div className="mx-auto grid w-full max-w-3xl gap-2.5 sm:grid-cols-2">
          {T3_BOOTS.map((b) => (
            <div key={b.name} className="glass flex items-center gap-3.5 rounded-2xl px-4 py-3">
              <img src={b.iconUrl} alt="" className="h-6 w-6 shrink-0 rounded-md border border-white/10 bg-neutral-900 object-cover" />
              <div className="min-w-0 flex-1">
                <p className="font-bold leading-tight truncate text-sm">{b.name}</p>
                <p className="text-[0.65rem] text-faint">from {b.from}</p>
                <p className="mt-0.5 text-xs text-muted leading-snug">{b.note}</p>
              </div>
            </div>
          ))}
          <div className="grid place-items-center rounded-2xl border border-accent/25 bg-accent/[0.07] px-4 py-3 text-center">
            <div>
              <p className="text-2xl font-black text-accent">10:00</p>
              <p className="text-xs uppercase tracking-wide text-muted">Upgrade unlocks</p>
            </div>
          </div>
        </div>
      </Slide>

      {/* 5 · Mage overhaul */}
      <Slide n={5} of={slides} title="The mage overhaul" sub="More raw AP everywhere, pen moved into dedicated items">
        <Rows rows={MAGE_ROWS} />
      </Slide>

      {/* 6 · Items to know */}
      <Slide n={6} of={slides} title="Items that change your builds" sub="Everything else worth knowing">
        <Rows rows={ITEM_ROWS} big />
      </Slide>

      {/* 7 · Runes */}
      <Slide n={7} of={slides} title="Runes: nerfed everywhere" sub="Keystone ratios took the biggest hit of the patch">
        <Rows rows={RUNE_ROWS} />
      </Slide>

      {/* 8 · Systems + outro */}
      <Slide n={8} of={slides} title="New rules of the game" sub="System changes in one look">
        <div className="mx-auto grid w-full max-w-4xl gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SYSTEMS.map((s) => (
            <div key={s.title} className="glass rounded-2xl p-4">
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent/15 text-accent">
                <Glyph name={s.glyph} size={16} />
              </span>
              <p className="mt-2.5 font-bold leading-tight">{s.title}</p>
              <p className="mt-1 text-sm leading-snug text-muted">{s.body}</p>
            </div>
          ))}
        </div>
        <div className="mx-auto mt-8 flex flex-col items-center gap-2 text-center">
          <img src="/logo.png" alt="WrTrueMeta" className="opacity-95" style={{ height: 32, width: "auto" }} />
          <p className="text-sm text-muted">
            Tier list, win rates and builds update for 7.2 ·{" "}
            <span className="font-semibold text-text">wrtruemeta.com</span>
          </p>
        </div>
      </Slide>
    </div>
  );
}

// ------------------------------------------------------------- components --

function Slide({ n, of, title, sub, children }: {
  n: number; of: number; title?: string; sub?: string; children: React.ReactNode;
}) {
  return (
    <section className="relative flex min-h-screen snap-start flex-col px-6 py-6">
      {/* slide chrome */}
      <div className="flex items-center justify-between">
        {n === 1 ? <span /> : <img src="/logo.png" alt="WrTrueMeta" style={{ height: 22, width: "auto" }} />}
        <span className="rounded-full border border-line bg-white/[0.04] px-3 py-1 text-[0.65rem] font-bold uppercase tracking-[0.18em] text-muted">
          Patch 7.2 · {n}/{of}
        </span>
      </div>
      {/* content */}
      <div className="flex flex-1 flex-col justify-center py-4">
        {title && (
          <div className="mb-6 text-center">
            <h2 className="text-3xl font-black tracking-tight sm:text-4xl">{title}</h2>
            {sub && <p className="mt-2 text-muted">{sub}</p>}
          </div>
        )}
        {children}
      </div>
      {/* watermark */}
      <p className="text-center text-xs text-faint">wrtruemeta.com</p>
    </section>
  );
}

function ChampCard({ title, color, champs, grid = false }: { title: string; color: string; champs: Champ[]; grid?: boolean }) {
  return (
    <div className="glass rounded-2xl p-4">
      <div className="flex items-center gap-2">
        <span className="h-3.5 w-1 rounded-full" style={{ background: color, boxShadow: `0 0 8px ${color}88` }} />
        <h3 className="text-xs font-bold uppercase tracking-[0.14em]" style={{ color }}>{title}</h3>
      </div>
      <div className={`mt-3 ${grid ? "grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4" : "flex flex-col gap-3"}`}>
        {champs.map((c) => (
          <div key={c.name} className="flex items-center gap-2.5">
            <span className="h-10 w-10 shrink-0 overflow-hidden rounded-full ring-1 ring-white/15">
              <img src={icon(c.slug, c.ddKey)} alt="" width={40} height={40} className="h-full w-full scale-[1.12] object-cover" />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-bold leading-tight">{c.name}</p>
              <p className="truncate text-xs leading-tight text-muted">{c.line}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const DIR: Record<string, { label: string; cls: string }> = {
  buff: { label: "Buff", cls: "bg-emerald-400/15 text-emerald-300" },
  nerf: { label: "Nerf", cls: "bg-rose-400/15 text-rose-300" },
  new: { label: "New", cls: "bg-sky-400/15 text-sky-300" },
  adjust: { label: "Adj", cls: "bg-white/10 text-muted" },
};

function Rows({ rows, big = false }: { rows: { id?: string; iconUrl?: string; name: string; change: string; dir: string }[]; big?: boolean }) {
  return (
    <div className="glass mx-auto w-full max-w-2xl overflow-hidden rounded-2xl">
      {rows.map((r, i) => {
        const d = DIR[r.dir] ?? DIR.adjust;
        return (
          <div key={r.name} className={`flex items-center gap-3 px-4 py-2 ${i > 0 ? "border-t border-line/50" : ""}`}>
            <span className={`w-12 shrink-0 rounded-md py-0.5 text-center text-[0.6rem] font-bold uppercase ${d.cls}`}>{d.label}</span>
            
            {/* Render direct image link if iconUrl is provided (e.g. Runes or Custom Items) */}
            {r.iconUrl ? (
              <img 
                src={r.iconUrl} 
                alt="" 
                className="h-6 w-6 shrink-0 rounded-md border border-white/10 object-cover bg-neutral-900" 
              />
            ) : r.id ? (
              /* Render Data Dragon item icon if item 'id' is provided */
              <img 
                src={itemIcon(r.id)} 
                alt="" 
                className="h-6 w-6 shrink-0 rounded-md border border-white/10 object-cover bg-neutral-900" 
              />
            ) : null}

            <span className={`shrink-0 font-bold ${big ? "w-56 text-[0.95rem]" : "w-48 text-sm"} truncate`}>{r.name}</span>
            <span className={`min-w-0 flex-1 truncate text-right text-muted ${big ? "text-[0.95rem]" : "text-sm"}`}>{r.change}</span>
          </div>
        );
      })}
    </div>
  );
}

function Glyph({ name, size = 18 }: { name: string; size?: number }) {
  const common = { width: size, height: size, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "star":
      return <svg {...common}><path d="M12 2.5l2.9 5.9 6.6 1-4.7 4.6 1.1 6.5L12 17.4l-5.9 3.1 1.1-6.5L2.5 9.4l6.6-1z" /></svg>;
    case "swap":
      return <svg {...common}><path d="M4 7h13M14 3.5L17.5 7 14 10.5M20 17H7M10 13.5L6.5 17l3.5 3.5" /></svg>;
    case "up":
      return <svg {...common}><path d="M6 13l6-6 6 6M6 19l6-6 6 6" /></svg>;
    case "zap":
      return <svg {...common}><path d="M13 2L4.5 13.5H11L9.5 22 19 10h-6.5z" /></svg>;
    case "crown":
      return <svg {...common}><path d="M3 17.5h18M4 16l-1-8 5.5 3.5L12 5l3.5 6.5L21 8l-1 8z" /></svg>;
    case "coin":
      return <svg {...common}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5v9M9.5 9.8c0-1 1.1-1.8 2.5-1.8s2.5.8 2.5 1.8c0 2.4-5 1.9-5 4.3 0 1 1.1 1.8 2.5 1.8s2.5-.8 2.5-1.8" /></svg>;
    default:
      return <svg {...common}><circle cx="12" cy="12" r="8" /></svg>;
  }
}