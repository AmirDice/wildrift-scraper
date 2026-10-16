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
  | { kind: "h3"; text: string }
  /** A simple table: a header row and string cells. */
  | { kind: "table"; head: string[]; rows: string[][] }
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

import { CURRENT_PATCH } from "@/lib/patch";

export interface BlogPost {
  slug: string;
  title: string;
  /** Meta description and the card blurb on the index. */
  description: string;
  /** ISO date. */
  date: string;
  /** ISO date of the last real revision, shown and sent as dateModified. */
  updated?: string;
  /** Unpublished: kept out of the index, the sitemap and search, but
   *  readable at its URL so it can be reviewed before it goes live. */
  draft?: boolean;
  /** Short label shown on the card. */
  tag: string;
  /** Opening paragraph, rendered above the body in a larger face. */
  lede: string;
  blocks: Block[];
}

export const POSTS: BlogPost[] = [
  {
    "slug": "patch-7-3b-analysis",
    "title": "Wild Rift Patch 7.3b: Senna and Hwei Nerfed, Assassins Buffed, and the Meta Shifts Again",
    "description": "Patch 7.3b nerfs Senna, Hwei, Nocturne and Yunara, buffs Yasuo, Jhin, Tryndamere and Volibear, and makes assassin items and burst runes stronger. What changed and what it means for the Wild Rift meta.",
    "date": "2026-10-16",
    "tag": "Patch analysis",
    "lede": "Wild Rift Patch 7.3b is here, and Riot is already making changes to the meta introduced in 7.3. Some of the strongest champions are getting pulled back, struggling picks are receiving much-needed buffs, and assassins might finally have a better chance of turning early leads into wins.",
    "blocks": [
      {
        "kind": "p",
        "text": "Senna, Hwei, Nocturne, and Yunara are among the champions receiving nerfs, while Yasuo, Jhin, Tryndamere, and Volibear are getting some help."
      },
      {
        "kind": "p",
        "text": "But the champion changes aren't the whole story. Cheaper assassin items, stronger burst runes, and adjustments to tank and support items could have just as much influence on the next few weeks of ranked."
      },
      {
        "kind": "p",
        "text": "Here's what's changing and what it means for the meta."
      },
      {
        "kind": "h2",
        "text": "Senna and Hwei Take Some Big Hits"
      },
      {
        "kind": "p",
        "text": "Let's start with two champions that have been particularly frustrating to deal with."
      },
      {
        "kind": "h3",
        "text": "Senna: Her Infinite Scaling Just Got Weaker"
      },
      {
        "kind": "p",
        "text": "Senna has been one of the standout picks of the recent meta, offering a combination of damage, range, healing, and scaling that makes her difficult to deal with as games go longer."
      },
      {
        "kind": "p",
        "text": "Patch 7.3b targets several parts of her kit."
      },
      {
        "kind": "ul",
        "items": [
          "Critical strike damage drops from 90% to 80%.",
          "Attack Damage gained per Black Mist stack decreases from 1.25 to 0.9.",
          "Piercing Darkness loses 20 base damage at every rank."
        ]
      },
      {
        "kind": "p",
        "text": "The Black Mist change is particularly important. At 100 stacks, Senna now gains 90 AD instead of 125 AD, a difference of 35 AD."
      },
      {
        "kind": "p",
        "text": "That's a significant amount of damage lost without even considering the reductions to her critical strikes and Q."
      },
      {
        "kind": "p",
        "text": "Senna will still bring plenty of utility, and her range scaling remains valuable. However, her ability to become a late-game damage threat while providing support utility has taken a noticeable hit."
      },
      {
        "kind": "p",
        "text": "**WRTrueMeta take:** This is one of the most meaningful nerfs in the patch. Senna should remain playable, but her damage-oriented builds are going to feel weaker, especially in longer games."
      },
      {
        "kind": "h3",
        "text": "Hwei: Less Damage, Less Shielding, Less Safety"
      },
      {
        "kind": "p",
        "text": "Hwei has been another major presence in Patch 7.3, and Riot is hitting several abilities rather than targeting just one."
      },
      {
        "kind": "p",
        "text": "His passive loses damage and AP scaling, his shielding is weaker, and Stirring Lights loses 10 base damage at every rank."
      },
      {
        "kind": "p",
        "text": "Crushing Maw is also getting nerfed:"
      },
      {
        "kind": "ul",
        "items": [
          "Cast range decreases from 7.5 to 7.",
          "Base damage decreases by 10 at every rank.",
          "AP ratio drops from 70% to 60%.",
          "Its hitbox has been adjusted."
        ]
      },
      {
        "kind": "p",
        "text": "These changes matter because Hwei's strength isn't limited to dealing damage. He can control space, protect teammates, and punish enemies trying to engage."
      },
      {
        "kind": "p",
        "text": "Reducing his shielding and crowd-control reach gives opponents more opportunities to fight back instead of being constantly kept at a distance."
      },
      {
        "kind": "p",
        "text": "**WRTrueMeta take:** Hwei is losing power across several parts of his kit, but his versatility hasn't disappeared. Players who rely on his range and control will need to be more careful with positioning."
      },
      {
        "kind": "h2",
        "text": "Nocturne and Yunara Are Also Getting Nerfed"
      },
      {
        "kind": "h3",
        "text": "Nocturne: Slower Clears and Fewer Ultimates"
      },
      {
        "kind": "p",
        "text": "Nocturne has been benefiting from the jungle changes introduced in Patch 7.3, and Riot is now looking to slow him down."
      },
      {
        "kind": "p",
        "text": "His health growth drops from 134 to 128 per level, while Duskbringer loses base damage at every rank. Its bonus Attack Damage is also reduced at earlier ranks, although the final rank receives a small increase."
      },
      {
        "kind": "p",
        "text": "The biggest change for many players will be his ultimate."
      },
      {
        "kind": "p",
        "text": "Paranoia's cooldown increases by 10 seconds at every rank, going from 110/90/70 to 120/100/80 seconds."
      },
      {
        "kind": "p",
        "text": "That means fewer opportunities to force fights, punish isolated carries, and influence lanes across the map."
      },
      {
        "kind": "p",
        "text": "Nocturne can still be dangerous when ahead, but he'll have to be more selective about when to commit."
      },
      {
        "kind": "h3",
        "text": "Yunara: Less Sustained Damage"
      },
      {
        "kind": "p",
        "text": "Yunara is receiving a fairly straightforward damage nerf."
      },
      {
        "kind": "p",
        "text": "Both the passive and active damage on Cultivation of Spirit lose 5 damage at every rank. Her ultimate cooldown also increases at ranks two and three."
      },
      {
        "kind": "p",
        "text": "The damage reduction might look small, but for a champion built around repeated attacks, losing damage on abilities used throughout a fight can add up."
      },
      {
        "kind": "p",
        "text": "Yunara should still have strong sustained damage, but her opponents will have slightly more room to survive extended trades."
      },
      {
        "kind": "h2",
        "text": "Yasuo, Jhin, Tryndamere, and Volibear Get Buffed"
      },
      {
        "kind": "p",
        "text": "Not everyone is leaving this patch weaker."
      },
      {
        "kind": "h3",
        "text": "Yasuo: More Damage and a Bigger Shield"
      },
      {
        "kind": "p",
        "text": "Yasuo hasn't had the easiest time adapting to the recent critical strike item changes, particularly after the removal of the crit version of Bloodthirster."
      },
      {
        "kind": "p",
        "text": "Patch 7.3b gives him two buffs:"
      },
      {
        "kind": "ul",
        "items": [
          "Critical strike damage increases from 90% to 95%.",
          "His passive shield's maximum value increases from 529 to 630."
        ]
      },
      {
        "kind": "p",
        "text": "The extra shield is especially useful against poke and during mid-to-late-game fights, while the crit damage increase improves his offensive potential."
      },
      {
        "kind": "p",
        "text": "This doesn't suddenly solve every difficult matchup, but it's a welcome improvement for Yasuo players."
      },
      {
        "kind": "h3",
        "text": "Jhin: His Damage Comes Online Earlier"
      },
      {
        "kind": "p",
        "text": "Jhin receives a change aimed at making his damage spikes arrive sooner."
      },
      {
        "kind": "p",
        "text": "His standard critical strike damage increases from 80% to 85%, while the missing-health damage on Whisper reaches its maximum value at level 10 instead of level 15."
      },
      {
        "kind": "p",
        "text": "That's an important difference for a champion who wants to capitalize on his mid-game item spikes."
      },
      {
        "kind": "p",
        "text": "Jhin no longer needs to wait until the very late game to access the full missing-health damage bonus."
      },
      {
        "kind": "p",
        "text": "With several marksman items also becoming cheaper, he'll be one to keep an eye on."
      },
      {
        "kind": "h3",
        "text": "Tryndamere: A More Reliable Crit Threat"
      },
      {
        "kind": "p",
        "text": "Tryndamere is receiving two useful buffs."
      },
      {
        "kind": "p",
        "text": "His Critical Strike Chance per Fury is now fixed at 0.5%, instead of scaling from 0.3% to 0.5% with level."
      },
      {
        "kind": "p",
        "text": "His Spinning Slash also gains more damage at later ranks, alongside an increase to its bonus AD ratio from 100% to 110%."
      },
      {
        "kind": "p",
        "text": "The Fury change should make his early-game critical strikes more consistent, while the Spinning Slash buff improves his damage as the game progresses."
      },
      {
        "kind": "p",
        "text": "This could make him more threatening in extended duels and side-lane fights."
      },
      {
        "kind": "h3",
        "text": "Volibear: Stronger Trades and Better Healing"
      },
      {
        "kind": "p",
        "text": "Volibear receives more AD scaling and improved healing on Frenzied Maul."
      },
      {
        "kind": "p",
        "text": "The ability's normal AD ratio increases from 100% to 110%, while its empowered damage ratio rises from 160% to 176%."
      },
      {
        "kind": "p",
        "text": "His empowered missing-health healing also gets a substantial increase at higher ability ranks, reaching 14% instead of 8%."
      },
      {
        "kind": "p",
        "text": "That extra sustain should help him survive longer during extended fights, especially when he's already taken damage."
      },
      {
        "kind": "p",
        "text": "Volibear has struggled to establish himself in the current meta, so these buffs are a step in the right direction."
      },
      {
        "kind": "h2",
        "text": "Assassins Could Be the Biggest Winners of Patch 7.3b"
      },
      {
        "kind": "p",
        "text": "While the champion changes are getting most of the attention, the item and rune adjustments might have a broader impact."
      },
      {
        "kind": "p",
        "text": "Riot has made it clear that assassins have been struggling to convert early advantages into victories."
      },
      {
        "kind": "p",
        "text": "Patch 7.3b attempts to address that."
      },
      {
        "kind": "p",
        "text": "**Youmuu's Ghostblade** is now 100 gold cheaper, dropping from 3000 to 2900."
      },
      {
        "kind": "p",
        "text": "**Electrocute** receives a base damage buff at early levels, increasing its damage floor from 40 to 60."
      },
      {
        "kind": "p",
        "text": "**Cheap Shot** also gets a cooldown reduction from 7 seconds to 5 seconds."
      },
      {
        "kind": "p",
        "text": "Individually, these aren't massive changes. Together, however, they give burst-focused champions more opportunities to capitalize on early fights."
      },
      {
        "kind": "p",
        "text": "Getting Youmuu's slightly earlier can make a difference in Wild Rift, where games move quickly and early item timings matter."
      },
      {
        "kind": "p",
        "text": "The Electrocute buff also makes short trades and early all-ins more threatening, particularly for champions that can reliably trigger it."
      },
      {
        "kind": "p",
        "text": "Don't expect every assassin to suddenly become top tier, but this is a clear attempt to make early aggression more rewarding."
      },
      {
        "kind": "h2",
        "text": "Tank and Support Items Are Getting Rebalanced"
      },
      {
        "kind": "p",
        "text": "Assassins aren't the only ones receiving item changes."
      },
      {
        "kind": "p",
        "text": "Several defensive and marksman items are also being adjusted."
      },
      {
        "kind": "table",
        "head": [
          "Item",
          "Patch 7.3b change"
        ],
        "rows": [
          [
            "Youmuu's Ghostblade",
            "Cost: 3000 → 2900"
          ],
          [
            "Locket of the Iron Solari",
            "Cost: 2600 → 2500, Health: 200 → 300"
          ],
          [
            "Thornmail",
            "Cost: 2700 → 2850"
          ],
          [
            "Warmog's Armor",
            "Passive Health requirement: 900 → 1250"
          ],
          [
            "Statikk Shiv",
            "Cost: 3000 → 2900, more Energized stacks per attack"
          ],
          [
            "Yun Tal Wildarrows",
            "Cost: 3100 → 3000"
          ]
        ]
      },
      {
        "kind": "h3",
        "text": "Tank Supports Get a Better Locket"
      },
      {
        "kind": "p",
        "text": "Locket of the Iron Solari receives one of the better item buffs this patch."
      },
      {
        "kind": "p",
        "text": "It costs 100 gold less and provides an additional 100 Health."
      },
      {
        "kind": "p",
        "text": "For tank supports looking to protect their carries, that's a fairly attractive improvement."
      },
      {
        "kind": "p",
        "text": "On the other hand, Thornmail is becoming 150 gold more expensive, delaying access to its armor and anti-healing effects."
      },
      {
        "kind": "p",
        "text": "Warmog's Armor also requires significantly more bonus Health to activate its passive, making it harder to use effectively in builds that aren't heavily invested in Health."
      },
      {
        "kind": "p",
        "text": "That change is particularly aimed at discouraging enchanters from picking up Warmog's too easily."
      },
      {
        "kind": "h3",
        "text": "Marksman Items Get Cheaper"
      },
      {
        "kind": "p",
        "text": "Statikk Shiv and Yun Tal Wildarrows both receive 100-gold price reductions."
      },
      {
        "kind": "p",
        "text": "Statikk Shiv also grants more Energized stacks through basic attacks, increasing from 5 to 7."
      },
      {
        "kind": "p",
        "text": "These changes should make both items more competitive with alternative marksman purchases."
      },
      {
        "kind": "p",
        "text": "However, the best option will still depend on the champion, their attack patterns, and what the enemy team is building."
      },
      {
        "kind": "p",
        "text": "A cheaper item isn't automatically the best item."
      },
      {
        "kind": "h2",
        "text": "Grasp and Aery Are Getting Weaker"
      },
      {
        "kind": "p",
        "text": "Two defensive rune options are also being nerfed."
      },
      {
        "kind": "p",
        "text": "**Grasp of the Undying** now deals 3% maximum Health damage instead of 3.3%, and its permanent Health gain decreases from 10 to 8."
      },
      {
        "kind": "p",
        "text": "This weakens both its lane trading and long-term scaling."
      },
      {
        "kind": "p",
        "text": "For champions that frequently activate Grasp, the reduced permanent Health gain will accumulate throughout a match."
      },
      {
        "kind": "p",
        "text": "**Aery** is also losing shielding power. Its base shield decreases from 25-120 to 20-100, while its AD and AP ratios stay unchanged."
      },
      {
        "kind": "p",
        "text": "These changes reduce some of the defensive value that tanks and enchanters have been getting from their rune setups."
      },
      {
        "kind": "p",
        "text": "Combined with the Electrocute and Cheap Shot buffs, Patch 7.3b looks like an attempt to bring more offensive options back into consideration."
      },
      {
        "kind": "h2",
        "text": "Jungle Changes: Raptors Are Harder to Steal"
      },
      {
        "kind": "p",
        "text": "There's also a small jungle adjustment worth mentioning."
      },
      {
        "kind": "p",
        "text": "Raptor camps are becoming tankier:"
      },
      {
        "kind": "ul",
        "items": [
          "Crimson Raptor base Health: 1000 → 1100.",
          "Crimson Raptor Health per level: 110 → 125.",
          "Small Raptor base Health: 500 → 550.",
          "Small Raptor Health per level: 55 → 65."
        ]
      },
      {
        "kind": "p",
        "text": "The idea is to make Raptors less vulnerable to quick mid-game and late-game invades."
      },
      {
        "kind": "p",
        "text": "Junglers who previously cleared these camps almost instantly may notice a small difference, especially when trying to steal enemy camps before rotating to an objective."
      },
      {
        "kind": "p",
        "text": "The changes aren't enough to completely reshape jungle pathing, but they could make opportunistic invades slightly less efficient."
      },
      {
        "kind": "h2",
        "text": "What Does Patch 7.3b Mean for the Meta?"
      },
      {
        "kind": "p",
        "text": "There are three changes worth watching closely."
      },
      {
        "kind": "p",
        "text": "First, some of the strongest ranged champions are losing power. Senna, Hwei, and Yunara have all received nerfs that should make them less oppressive, although their actual performance will depend on how players adapt."
      },
      {
        "kind": "p",
        "text": "Second, Riot is making early burst damage more rewarding. The cheaper Youmuu's Ghostblade and buffs to Electrocute and Cheap Shot give assassins a better chance of converting successful early fights into meaningful advantages."
      },
      {
        "kind": "p",
        "text": "Finally, itemization is shifting again. Several marksman and support items are becoming cheaper, while popular defensive options like Thornmail and Warmog's Armor are facing restrictions."
      },
      {
        "kind": "p",
        "text": "It's still too early to declare the biggest winners and losers based on patch notes alone. A champion getting buffed doesn't necessarily mean their win rate will increase significantly, especially when their common opponents and items are changing at the same time."
      },
      {
        "kind": "p",
        "text": "That's where the actual match data becomes important."
      },
      {
        "kind": "h2",
        "text": "Track the Patch 7.3b Meta on WRTrueMeta"
      },
      {
        "kind": "p",
        "text": "Patch notes tell us what Riot changed. They don't always tell us how those changes will affect ranked games."
      },
      {
        "kind": "p",
        "text": "At **WRTrueMeta**, we track Wild Rift leaderboard data across EU, NA, and CN to help players understand how champions are performing."
      },
      {
        "kind": "p",
        "text": "As new Patch 7.3b data becomes available, you can explore champion win rates, regional tier lists, popular builds, and build recommendations based on the current meta."
      },
      {
        "kind": "p",
        "text": "Whether you're looking for the strongest junglers, trying to find a better build for your main, or wondering if a recently nerfed champion is still worth playing, the numbers will help paint a clearer picture."
      },
      {
        "kind": "cta",
        "href": "/tier-list",
        "label": "Explore the latest Wild Rift meta",
        "text": "Champion win rates, regional tier lists and builds from the top players in EU, NA and China."
      },
      {
        "kind": "p",
        "text": "Source: Riot Games, Wild Rift Patch Notes 7.3b, October 14, 2026."
      }
    ]
  },
  {
    slug: "best-junglers-patch-7-2a",
    title: `The best junglers in Wild Rift right now (patch ${CURRENT_PATCH})`,
    description:
      "The strongest Wild Rift junglers this patch, ranked by the real win rates of each champion's best players rather than by overall pick rate.",
    date: "2026-07-23",
    updated: "2026-10-16",
    tag: "Tier list",
    lede:
      "Jungle decides more games than any other role in Wild Rift, and it is the role where the gap between what is popular and what actually wins is widest. These are the junglers carrying the current patch.",
    blocks: [
      {
        kind: "p",
        text:
          "Every ranking below comes from the same place: the top 30 ranked players on each champion in every region, with their win rates confidence-adjusted so a 12-game hot streak cannot outrank a 300-game grinder. That matters more in jungle than anywhere else, because jungle win rates are dragged down hardest by players who picked the role up last week.",
      },
      { kind: "h2", text: "The best junglers this patch" },
      {
        kind: "champions",
        source: "role",
        role: "Jungle",
        limit: 10,
        note: "Ranked by confidence-adjusted win rate across each champion's best players in every region.",
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
        href: "/regions#brackets",
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
        href: "/regions#china-ahead",
        label: "See the full meta gap",
        text: "Every champion where China's top elo and the Western ladder disagree, in both directions.",
      },
    ],
  },
  {
    slug: "best-baron-laners-patch-7-2a",
    title: `The best Baron laners in Wild Rift (patch ${CURRENT_PATCH})`,
    description:
      "The strongest Wild Rift Baron lane champions this patch, ranked by the real win rates of each champion's best players, plus who to pick into a bad matchup.",
    date: "2026-07-19",
    updated: "2026-10-16",
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
        note: "Ranked by confidence-adjusted win rate across each champion's best players in every region.",
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

/** Published posts, newest first. Drafts are left out. */
export function getPosts(): BlogPost[] {
  return POSTS.filter((post) => !post.draft).sort((left, right) => right.date.localeCompare(left.date));
}

export function getPost(slug: string): BlogPost | null {
  return POSTS.find((post) => post.slug === slug) ?? null;
}

/** Rough reading time, for the post header. */
export function readingMinutes(post: BlogPost): number {
  const words = [post.lede, ...post.blocks.map((block) => ("text" in block ? block.text
    : block.kind === "ul" ? block.items.join(" ") : ""))]
    .join(" ")
    .split(/\s+/).length;
  return Math.max(2, Math.round(words / 190));
}
