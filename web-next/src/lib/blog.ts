/**
 * The blog.
 *
 * Posts are data, not prose files: every ranked list in a post is described
 * declaratively ({ kind: "champions", source: "role", role: "Jungle" }) and
 * resolved from the live dataset at render time. That way a post about the
 * best junglers this patch does not go stale the moment the next scrape lands,
 * and no ranking on the site can disagree with any other.
 *
 * To add a post: append an entry to POSTS. `date` is the publish date, used for
 * ordering and for the article metadata.
 */

export type Block =
  | { kind: "p"; text: string }
  | { kind: "h2"; text: string }
  | { kind: "ul"; items: string[] }
  | { kind: "quote"; text: string }
  | { kind: "cta"; href: string; label: string; text: string }
  | {
      /** A ranked champion list resolved from live site data. */
      kind: "champions";
      source: "role" | "climbing" | "stompers" | "rising" | "adjusted" | "unchanged" | "otp";
      /** Required when source is "role". */
      role?: string;
      limit?: number;
      /** Rendered under the list as the "why these" note. */
      note?: string;
    };

export interface BlogPost {
  slug: string;
  title: string;
  /** Meta description and the card blurb on the index. */
  description: string;
  /** ISO date. */
  date: string;
  /** Short label shown on the card. */
  tag: string;
  /** Opening paragraph, rendered above the body in a larger face. */
  lede: string;
  blocks: Block[];
}

export const POSTS: BlogPost[] = [
  {
    slug: "best-junglers-patch-7-2a",
    title: "The best junglers in Wild Rift right now (patch 7.2a)",
    description:
      "The strongest Wild Rift junglers this patch, ranked by the real win rates of each champion's 50 best players rather than by overall pick rate.",
    date: "2026-07-23",
    tag: "Tier list",
    lede:
      "Jungle decides more games than any other role in Wild Rift, and it is the role where the gap between what is popular and what actually wins is widest. These are the junglers carrying patch 7.2a.",
    blocks: [
      {
        kind: "p",
        text:
          "Every ranking below comes from the same place: the top 50 ranked players on each champion, with their win rates confidence-adjusted so a 12-game hot streak cannot outrank a 300-game grinder. That matters more in jungle than anywhere else, because jungle win rates are dragged down hardest by players who picked the role up last week.",
      },
      { kind: "h2", text: "The best junglers this patch" },
      {
        kind: "champions",
        source: "role",
        role: "Jungle",
        limit: 10,
        note: "Ranked by confidence-adjusted win rate across each champion's 50 best players.",
      },
      { kind: "h2", text: "Junglers that scale with your own rank" },
      {
        kind: "p",
        text:
          "A champion's win rate is not one number. Some junglers get better the higher you climb, because their power is locked behind decisions the average player does not make. Those are the ones worth investing in if you are climbing.",
      },
      {
        kind: "champions",
        source: "climbing",
        limit: 5,
        note: "Biggest win-rate gain between China's cumulative Diamond+ and Challenger samples.",
      },
      { kind: "h2", text: "Junglers that stomp low elo and fall off" },
      {
        kind: "p",
        text:
          "The mirror image: champions with a strong win rate on the full ladder that gets noticeably worse in top-elo games. Good picks to climb with today, bad picks to spend a season mastering.",
      },
      {
        kind: "champions",
        source: "stompers",
        limit: 5,
        note: "Largest drop-off from China's cumulative Diamond+ sample to Challenger.",
      },
      {
        kind: "cta",
        href: "/build?tab=generate",
        label: "Generate a jungle build",
        text:
          "Picked one? Generate a build around your clear path, your power spike and the enemy team rather than copying a static item list.",
      },
    ],
  },
  {
    slug: "champions-riot-changes-most",
    title: "The Wild Rift champions Riot cannot stop changing",
    description:
      "Which Wild Rift champions have been buffed and nerfed the most, which have been left alone the longest, and the one champion that has never received a single change.",
    date: "2026-07-22",
    tag: "Balance",
    lede:
      "We counted every champion entry in the official Wild Rift patch notes. The spread is wider than you would guess: some champions have been touched dozens of times, and at least one has never been touched at all.",
    blocks: [
      { kind: "h2", text: "Most adjusted champions" },
      {
        kind: "p",
        text:
          "These are patch-note appearances, counting both standard balance changes and mode-only tuning. A high number is not automatically a sign of a broken champion; it usually means the kit has a knob Riot keeps having to turn.",
      },
      { kind: "champions", source: "adjusted", limit: 10 },
      { kind: "h2", text: "Left alone the longest" },
      {
        kind: "p",
        text:
          "The other end of the list. A champion that has gone hundreds of days without a balance change is either quietly well-tuned or quietly forgotten, and the win rates usually tell you which.",
      },
      { kind: "champions", source: "unchanged", limit: 10 },
      {
        kind: "cta",
        href: "/changes-report",
        label: "See the full balance report",
        text: "The whole picture on one page, including the champion that has never been changed once.",
      },
    ],
  },
  {
    slug: "best-champions-to-climb-with",
    title: "The best Wild Rift champions to climb with this patch",
    description:
      "Wild Rift champions with the highest win rates for climbing, split into picks that get stronger as you rank up and picks that stomp low elo.",
    date: "2026-07-21",
    tag: "Climbing",
    lede:
      "The best champion for climbing is not the highest win-rate champion on the ladder. It is the one whose win rate holds up at the rank you are actually trying to reach.",
    blocks: [
      { kind: "h2", text: "Picks that get better the higher you climb" },
      {
        kind: "p",
        text:
          "These champions gain the most win rate between China's cumulative Diamond+ and Challenger samples. They reward mastery, which means they are worth a long-term investment and they will feel bad for the first fifty games.",
      },
      { kind: "champions", source: "climbing", limit: 8 },
      { kind: "h2", text: "Picks that win now" },
      {
        kind: "p",
        text:
          "Champions that perform best on the ladder as a whole. If you are stuck below your target rank and want the shortest route out, this is the list to take from.",
      },
      { kind: "champions", source: "stompers", limit: 8 },
      { kind: "h2", text: "One-trick material" },
      {
        kind: "p",
        text:
          "If you would rather learn one champion properly than chase the meta every patch, these are the champions where dedicated players separate themselves furthest from the average.",
      },
      { kind: "champions", source: "otp", limit: 8 },
      {
        kind: "cta",
        href: "/ranks",
        label: "See win rate by skill bracket",
        text: "The full breakdown of how every champion performs from Diamond+ through Challenger, with CN Legendary shown separately.",
      },
    ],
  },
  {
    slug: "china-meta-ahead-of-the-west",
    title: "China is a patch ahead: the Wild Rift picks to learn early",
    description:
      "Champions rated far higher in China's top Wild Rift ranks than in the West, and the picks the West still overrates. Learn them before the meta catches up.",
    date: "2026-07-20",
    tag: "Meta",
    lede:
      "China's Wild Rift server plays the meta before the rest of the world does. Comparing the two datasets is the cheapest edge available: the picks rising in Chinese top elo are usually the picks everyone else is on in two patches' time.",
    blocks: [
      { kind: "h2", text: "Rising in China, ignored in the West" },
      {
        kind: "p",
        text:
          "Each of these champions is rated meaningfully higher by China's Challenger sample than by the Western dataset. That gap is the lead time you get to learn them.",
      },
      { kind: "champions", source: "rising", limit: 8 },
      { kind: "h2", text: "How to use this list" },
      {
        kind: "ul",
        items: [
          "Pick one champion from the list, not four. The edge comes from being early on something you can actually play.",
          "Check the champion page for the matchups before you first-pick it into a bad lane.",
          "Build it around the enemy comp rather than around the popular item order, which will still be tuned for the old meta.",
        ],
      },
      {
        kind: "cta",
        href: "/rising",
        label: "See the full meta gap",
        text: "Every champion where China's top elo and the Western ladder disagree, in both directions.",
      },
    ],
  },
  {
    slug: "best-baron-laners-patch-7-2a",
    title: "The best Baron laners in Wild Rift (patch 7.2a)",
    description:
      "The strongest Wild Rift Baron lane champions this patch, ranked by the real win rates of each champion's best players, plus who to pick into a bad matchup.",
    date: "2026-07-19",
    tag: "Tier list",
    lede:
      "Baron lane is the most isolated role in Wild Rift, which makes champion choice matter more there than anywhere else. Get the matchup wrong and no amount of mechanics saves the lane.",
    blocks: [
      { kind: "h2", text: "The best Baron laners this patch" },
      {
        kind: "champions",
        source: "role",
        role: "Baron",
        limit: 10,
        note: "Ranked by confidence-adjusted win rate across each champion's 50 best players.",
      },
      { kind: "h2", text: "Losing the matchup?" },
      {
        kind: "p",
        text:
          "Most lost Baron lanes are lost in champion select and then made worse by a build that ignores the enemy entirely. If you are already locked in, the fix is the build: the right early resistance or the right anti-heal item swings a lane far more than another five minutes of trading practice.",
      },
      {
        kind: "cta",
        href: "/build?tab=counter",
        label: "Build against your lane opponent",
        text: "Tell it who you are facing and it rebuilds your items, boots and runes around beating exactly that.",
      },
    ],
  },
];

export function getPosts(): BlogPost[] {
  return [...POSTS].sort((left, right) => right.date.localeCompare(left.date));
}

export function getPost(slug: string): BlogPost | null {
  return POSTS.find((post) => post.slug === slug) ?? null;
}

/** Rough reading time, for the post header. */
export function readingMinutes(post: BlogPost): number {
  const words = [post.lede, ...post.blocks.map((block) => ("text" in block ? block.text : ""))]
    .join(" ")
    .split(/\s+/).length;
  return Math.max(2, Math.round(words / 190));
}
