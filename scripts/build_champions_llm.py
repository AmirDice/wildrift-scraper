"""LLM-authored optimal builds + runes per champion, grounded & validated.

Per-class build VARIANTS (not a fixed balanced+damage for everyone):
  Assassin  -> balanced, oneshot
  Bruiser   -> balanced, tanky, damage
  Marksman  -> crit, balanced, damage
  Mage      -> burst, balanced, battlemage
  Tank      -> tanky, damage
  Enchanter -> utility, poke

For each champion we give the model the full scraped kit + item/rune pools + the
item-exclusivity (mutex) rules, plus KIT FLAGS: deterministic synergy hooks
detected from the ability text (move-speed -> damage conversion, short-CD spam
engines, %max-HP damage, ...) that the model MUST address. Grounding: the model
may ONLY use items/runes from the pools; every slug is validated, and
each build is checked against mutex + rune-page + scaling rules, with a repair
round-trip on failures.

--best-of N generates N candidates and a judge pass picks the strongest build
per variant before validation (self-consistency beats a single sample).

Providers: --provider deepseek (default; needs DEEPSEEK_API_KEY), gemini (needs
GEMINI_API_KEY / GOOGLE_API_KEY), or ollama (local; needs `ollama serve`).

Run:
    python -m scripts.build_champions_llm --only "Hecarim" --best-of 3
    python -m scripts.build_champions_llm --provider gemini
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path

import requests

from web.advisor import env as advisor_env
from web.advisor import itemmeta as advisor_itemmeta
from web.advisor import profiles as advisor_profiles
from web.advisor import summoners as advisor_summoners

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
RUNES = ROOT / "data" / "runes.json"
CHAMPS = ROOT / "data" / "champions_wr.json"
CHAMPION_OVERRIDES = ROOT / "data" / "champion_stat_overrides.json"
RULES = ROOT / "data" / "item_rules.json"
SITE = ROOT / "web-next" / "src" / "data" / "site.json"
OUT = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"  # what the frontend reads

# ollama default sized for an 8GB-RAM machine: qwen2.5 3B (~2GB) is the smallest
# model that reliably follows our JSON schema over a ~13K-token prompt.
DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-flash",
    "gemini": "gemini-2.5-flash",
    "ollama": "qwen2.5:3b-instruct",
}
OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MAX_OUTPUT_TOKENS = 384_000

_RULES_EARLY = json.loads(RULES.read_text(encoding="utf-8")) if RULES.exists() else {}
# Reactive anti-comp items: allowed in situational swaps, never in the core build.
SITUATIONAL_ONLY = set((_RULES_EARLY.get("situationalOnly") or {}).get("slugs") or [])
# Neither reactive nor core: legal late, with a reason. See the rules file.
LATE_STRATEGIC: dict[str, dict] = {
    slug: cfg for slug, cfg in (_RULES_EARLY.get("lateGameStrategic") or {}).items()
    if not slug.startswith("_") and isinstance(cfg, dict)
}

# Minor-rune slot structure: a page takes exactly ONE minor from each of the
# primary tree's 3 slots. The flex minor is not slot-tied.
_SLOTS_PATH = ROOT / "data" / "rune_slots.json"
RUNE_SLOTS = (json.loads(_SLOTS_PATH.read_text(encoding="utf-8")) if _SLOTS_PATH.exists() else {}).get("trees", {})
SLOT_OF: dict[str, int] = {}
for _tree, _slots in RUNE_SLOTS.items():
    for _s, _names in _slots.items():
        for _n in _names:
            SLOT_OF[_n] = int(_s)

# --- per-class build variants ---------------------------------------------
# Base preset set per class. "standard" (the best all-around build for a typical
# game) is always first; the rest are the champion-adaptive leans. Some presets
# are appended only when the kit can actually pull them off (see variants_for).
VARIANT_SETS = {
    "Assassin":  ["standard", "oneshot"],
    "Bruiser":   ["standard", "damage", "tanky"],
    "Fighter":   ["standard", "damage", "tanky"],
    # No "survivability" for marksmen: on an ADC it collapses into a worse
    # "standard" (standard already weighs survival at 40% and adapts to the
    # kit), so it produced a duplicate build with a different label. It stays on
    # ENCHANTERS, where "protect support + survive" is a genuinely distinct job.
    "Marksman":  ["standard", "dps", "crit"],
    "Mage":      ["standard", "burst"],
    "Tank":      ["standard", "tanky"],
    "Enchanter": ["standard", "utility"],
}
DEFAULT_VARIANTS = ["standard", "damage"]

# Variant briefs. The four curated IDs (standard/damage/tanky/offmeta) remain
# compatible with stored records. ``offmeta`` is no longer forced novelty: it is
# requested only when the reviewed profile exposes a credible, mechanically
# supported secondary path, and is shown as Alternative Path.
VARIANT_DESC = {
    "standard":   "STANDARD: the highest-confidence all-around build for an unknown enemy team. "
                  "Optimise the champion's normal combat pattern, first-three-item power curve, "
                  "role, general reliability, target access, resource needs, and enough "
                  "survivability to perform their job. Do not force a fixed offense/defense split",
    "oneshot":    "maximum burst to instantly delete a priority target",
    "damage":     "AGGRESSIVE: a damage-focused but dependable unknown-enemy build. Maximise "
                  "practical damage while preserving enough target access, resource availability, "
                  "combat uptime and survivability to execute the champion's normal combat "
                  "pattern. For melee divers and bruisers, do not sacrifice so much durability "
                  "that the champion commonly dies before completing their repeated abilities or "
                  "second rotation. This is NOT automatically full lethality, full crit or glass "
                  "cannon: choose the damage structure that fits the kit",
    "dps":        "sustained auto-attack damage per second for extended fights",
    "survivability": "protect-support build that also survives dives, for enchanters whose "
                     "job is keeping allies alive rather than dealing damage",
    "antitank":   "anti-tank build with %max-HP and armor/magic penetration to melt the frontline",
    "burst":      "burst build to one-shot squishies (only when the kit can truly burst)",
    "poke":       "poke-damage build for chipping enemies before fights",
    "sustained":  "sustained / drain damage build for longer trades",
    "tanky":      "DURABLE: a durability-focused version of the champion's LEGITIMATE build. Add "
                  "meaningful survivability while retaining the champion's essential damage "
                  "engine, threat, engage, protection, healing, crowd control or other role "
                  "function. A Bruiser, Assassin, Marksman or Mage must NOT become an ignorable "
                  "full tank; full tank is appropriate only when the class and kit genuinely "
                  "support it",
    "crit":       "crit-based build stacking crit chance + crit damage",
    "battlemage": "sustained AP damage / drain-tank build",
    "utility":    "team-support build maximising heal / shield / CC uptime",
    "offmeta":    "ALTERNATIVE PATH: use ONLY the exact reviewed alternativeBuildPath in the "
                  "champion's BUILD IDENTITY PROFILE. It must be a coherent secondary AP, AD, "
                  "hybrid, on-hit, crit or primary-stat durable path whose repeated combat "
                  "engine supports it. Never invent a wrong-stat novelty from one incidental "
                  "ratio. If the approved path cannot be built coherently from the supplied "
                  "items, do not substitute a different experiment",
}

# User-facing names for the variants, mapped from the legacy IDs the records and
# frontend still key on. Only the label the player reads changes; the stored ID
# does not, so nothing needs migrating. Covers every id in VARIANT_SETS /
# variants_for so no variant falls back to a raw .title() ("Dps", "Antitank").
VARIANT_LABEL = {
    "standard": "Standard",
    "damage": "Aggressive",
    "tanky": "Durable",
    "offmeta": "Alternative Path",
    # Class-specific emphases (marksman/mage/assassin/enchanter), unchanged in
    # scope -- an ADC still gets crit, DPS, burst and anti-tank.
    "dps": "Sustained DPS",
    "crit": "Crit",
    "burst": "Burst",
    "oneshot": "One-shot",
    "antitank": "Anti-tank",
    "utility": "Utility",
    "survivability": "Protective",
    "poke": "Poke",
    "sustained": "Sustained",
    "battlemage": "Battlemage",
}

# Alternative paths are credible but intentionally separate from the champion's
# primary trusted path. The approval marker emitted during validation is the
# authority the frontend uses; legacy Experimental records do not gain it.
VARIANT_TRUST_TIER = {
    "offmeta": "alternative",
}


def variants_for(name: str, champ_class: str, role: str = "") -> list[str]:
    """Preset set for a champion: class AND role decide it (a Mage bot-lane and a
    Mage support want different builds), plus the leans the kit can pull off."""
    # Variant routing must not depend on the retired fight engine. These classes
    # have legitimate burst itemizations; the LLM decides whether each variant
    # fits the exact kit from the complete ability text.
    burst_ok = champ_class in ("Assassin", "Mage", "Marksman")
    support = role == "Support"

    # Poke is only offered when the champion can actually apply repeatable ranged
    # pressure -- not to every Mage/Enchanter. A melee assassin classed as Mage
    # (Akali) fails this and gets a credible alternative instead.
    poke_ok = advisor_profiles.poke_eligibility(name)["eligible"]

    if name == "Master Yi":
        # His Assassin class describes target access, not itemisation. Yi is a
        # repeated-attack carry, so generic lethality/one-shot routing is wrong.
        base = ["standard", "dps", "crit", "antitank"]
    elif support and champ_class == "Enchanter":
        # Protect supports (Lulu, Soraka, Milio): their job is keeping allies
        # alive, so no damage build. Full support, or support + survivability.
        base = ["standard", "utility", "survivability"]
        if burst_ok and poke_ok:
            base.append("poke")         # outliers with real damage (e.g. Nami)
    elif support and champ_class == "Tank":
        # Support tanks (Nautilus, Leona): frontline, but several can go AP/bruiser.
        base = ["standard", "tanky", "damage"]
    elif support and champ_class in ("Mage", "Marksman"):
        # Carry supports (Lux, Seraphine, Senna): they do want damage, but still
        # need a support option and a way to survive.
        base = ["standard", "damage", "survivability", "utility"]
        if burst_ok:
            base.append("burst")
    else:
        base = list(VARIANT_SETS.get(champ_class, DEFAULT_VARIANTS))
        # every tank can trade some durability for damage (AP or bruiser)
        if champ_class == "Tank" and "damage" not in base:
            base.append("damage")
        if champ_class in ("Bruiser", "Fighter", "Marksman") and burst_ok and "burst" not in base:
            base.append("burst")        # e.g. Lucian can burst, Jinx cannot
        if champ_class == "Marksman":
            base.append("antitank")     # any ADC can itemise %HP / armor pen
        if champ_class in ("Mage", "Enchanter") and poke_ok:
            base.append("poke")         # only genuine ranged pokers
        elif champ_class in ("Mage", "Enchanter") and not poke_ok and "burst" not in base:
            # A melee caster that loses poke still needs a credible alternative;
            # burst suits melee assassins classed as Mage (Akali, Diana).
            base.append("burst")
    # Optional, reviewed secondary path. A missing path is a positive decision:
    # forcing AP/crit/tank novelty from one incidental ratio caused the Rammus,
    # Fiora and Irelia failures this layer exists to prevent.
    if advisor_profiles.alternative_path(name):
        base.append("offmeta")

    # de-dupe, preserve order
    seen, out = set(), []
    for v in base:
        if v not in seen:
            seen.add(v); out.append(v)
    return out

# role -> extra rune guidance
ROLE_RUNE_HINTS = {
    # Overgrowth is a legitimate jungle option, not a default. "Strongly favour
    # it" put it in essentially every page, including damage builds where its
    # flat HP does nothing for the build's job. State the fact, let the model
    # decide.
    "Jungle": "This is a JUNGLER: Overgrowth (Resolve) stacks HP off monster kills, so "
              "it scales well with jungle farm. Consider it for durable builds; do NOT "
              "default to it on damage or glass builds, where HP does not serve the "
              "build's job.",
}

# Champions with a scraped kit but no site entry yet (no EU leaderboard data),
# so class/role can't come from site.json. Keep this tiny map current.
CLASS_FALLBACK: dict[str, tuple[str, str]] = {
    "Skarner": ("Tank", "Jungle"),
    "Yunara": ("Marksman", "Dragon"),
    "Cho'Gath": ("Tank", "Baron"),
    # Rhaast is a different champion from blue Kayn, and the class drives which
    # build variants get authored: the Assassin set (balanced/oneshot) is the
    # wrong question to ask about a bruiser who heals off max-Health damage.
    "Kayn (Rhaast)": ("Bruiser", "Jungle"),
}

# Summoner spells come from web/advisor/summoners.py, shared with the live
# advisor: the rules are flat enough to apply in code, and two copies of them
# would be two things to keep in sync.
_DD_SPELL = advisor_summoners._DD_SPELL
SUMMONERS = advisor_summoners.SPELLS

SYSTEM = (
    "You are a top-tier Wild Rift theorycrafter. For a champion you design several "
    "BUILD VARIANTS (given per champion) that synergise with the champion's passive "
    "and abilities. Hard rules:\n"
    "Each variant should be the loadout with the highest expected practical win rate "
    "under the supplied champion data, current item pool, role and variant brief. Do not "
    "claim statistical superiority unless the supplied data supports it: you are making a "
    "strategic recommendation, not proving an optimum.\n"
    "- SYNERGY IS A MAJOR FACTOR, NOT AN AUTOMATIC WINNER. Before choosing anything, mine "
    "the PASSIVE and each ability for stat conversions and interactions (e.g. 'gains AD "
    "from bonus move speed' means move-speed items/runes have extra offensive value here; "
    "max-health scaling rewards HP stacking; ability-spam kits use haste/mana). Write "
    "these hooks in synergyNotes FIRST. A direct interaction with the kit is a strong "
    "positive, but it does NOT by itself make an item optimal: every synergistic item is "
    "still compared on complete stats, passive reliability, purchase timing, completion "
    "cost, activation delay, opportunity cost, role and playstyle fit, how OFTEN the "
    "interaction actually fires in a 15-20 minute match, and whether the champion survives "
    "long enough to use it. Do not pick an item because one sentence in its passive matches "
    "one sentence in the kit.\n"
    "- PER-CAST / RESOURCE ITEMS (Manamune/Muramana, Spear of Shojin, Archangel's, spellblade, "
    "ability haste): a short-cooldown mana user should make you EVALUATE these, never treat "
    "them as automatically core. Account for tear stacking time, transformation timing, weak "
    "immediate combat value, whether the item transforms before the game is usually decided, "
    "mana availability during real champion combat, and whether an earlier COMPLETED item "
    "gives a stronger first or second spike. Select Manamune only when its expected "
    "transformation timing and repeated proc value outweigh an earlier completed combat item.\n"
    "- STAT CONVERSIONS raise a stat's value, they do not make every item carrying that stat "
    "efficient. Compare converted-stat options more favourably than for an ordinary champion, "
    "but select them only when their complete package beats the alternatives. Do NOT force a "
    "variant to be built around a converted stat.\n"
    "- READ THE SUPPLIED PROFILES, and trust them over your impression of the champion. "
    "The champion block carries a COMBAT PROFILE and a SCALING PROFILE derived from that "
    "kit's ability text, cooldowns and parsed ratios. A ratio existing does NOT make items "
    "granting that stat viable: `buildPathViability` labels each stat core / secondary / "
    "not_viable and that label OVERRIDES the raw ratio share -- only 'core' can anchor a "
    "normal primary-path build. The sole exception is an explicitly supplied, reviewed "
    "`alternativePath`, whose listed anchorStats may anchor Alternative Path only. "
    "`repeatedOnHitReliance` separates a kit that applies an on-hit effect ONCE from one "
    "whose damage depends on applying it over and over -- only the latter wants attack "
    "speed and on-hit stacking.\n"
    "- BUILD IDENTITY IS AUTHORITATIVE. The BUILD IDENTITY PROFILE names the champion's "
    "primary combat engine, main damage source, core stats and approved build paths. "
    "Optimise the source that repeats throughout a fight (autos, passive, basic abilities "
    "or resets), not whichever isolated ability prints the largest ratio. An ultimate or "
    "defensive/utility spell with one large AP ratio cannot redefine an AD auto-attacker; "
    "a magic-damage tank can still have Armor/Health rather than AP as its build identity. "
    "Every normal variant must stay inside approvedBuildPaths. Alternative Path exists "
    "only when alternativePath is supplied, and must follow that exact path.\n"
    "- RESOURCE LOOP: check the kit's spam pattern. A champion that casts cheap "
    "abilities every few seconds (short-CD spam) turns mana-scaling and per-cast items "
    "(Manamune/Muramana, Archangel's, Spear of Shojin, spellblade) into a compounding "
    "damage loop, and ability haste into raw DPS. A champion with long cooldowns or "
    "no mana gets little from these. Build around the loop, not just raw stats.\n"
    "- Wild Rift is burst-heavy and matches average 15-20 minutes: favour gold-efficient "
    "items and a realistic build order (item 1 is rushed first). Don't plan for 40-minute games.\n"
    "- BUILD ORDER IS TIMING, NOT A RANKING. Slot 1 is bought first; slot 5 is bought last "
    "and in many games never finished. Order each item by WHEN its effect is needed: the "
    "item that wins the early lane, the first objective or the first skirmishes comes "
    "first, and expensive scaling or finisher items come last. A cheap early-power item "
    "sitting in slot 4 or 5 is a mistake -- if its value is early it goes early, and if it "
    "is not worth an early slot it does not belong in the five at all.\n"
    "- SITUATIONAL SWAPS NEED REAL TIMING. Each swap replaces a specific coreBuild item, "
    "so it is bought at that item's position. Most threats have to be answered by the 2nd "
    "or 3rd purchase; a swap that only happens at item 5 arrives after the game is decided. "
    "Spread the swaps across the build instead of parking them all on the last item, and "
    "put each one where that threat actually has to be answered.\n"
    "- Account for the champion's damage type and ability scalings (AD/AP/on-hit/crit/"
    "max-health/attack-speed) and per-level base stats.\n"
    "- Each variant is 5 items + 1 boots. Summoner spells are added afterwards and are "
    "not yours to pick. There is NO boot "
    "enchantment: patch 7.2 removed enchantments and tied active effects to champion "
    "classes instead, so actives (Locket, Zhonya's, Quicksilver Sash, Stridebreaker) are "
    "ordinary items you pick in the 5 slots.\n"
    "- BOOTS ARE A REAL PICK, not an afterthought. Choose the TIER-2 boots whose stats AND "
    "passive fit this champion and this build, exactly as you would an item: Boots of "
    "Dynamism or Boots of Mana when the penetration suits your damage type, Ionian for "
    "cooldowns, Gluttonous for sustain, Swiftmarch/Berserker as the class fits. Each "
    "upgrades into its tier-3 version at 10:00, so the tier-2 you choose decides the "
    "tier-3 you end on.\n"
    "- DEFENSIVE BOOTS ARE NOT MAIN BOOTS FOR DAMAGE CLASSES. For a Bruiser, Marksman or "
    "Assassin, the MAIN boots must NOT be Mercury's Treads or Plated Steelcaps -- those "
    "sacrifice the kill pressure the whole build exists for. Offer them ONLY as a "
    "situationalBoots swap ('vs CC/AP' / 'vs repeated AD attacks') for those classes. "
    "Tanks should normally take defensive boots because frontline uptime is part of their "
    "job; an Armor-scaling retaliation tank should strongly prefer Plated Steelcaps. Use "
    "Ionian or damage boots on a tank only when the BUILD IDENTITY PROFILE and build reason "
    "show why cooldown/damage value beats frontline uptime.\n"
    "- DO NOT CHOOSE SUMMONER SPELLS. They are assigned deterministically from the "
    "champion, role and class after you answer, and any you return are discarded.\n"
    "RULES COME IN THREE TIERS. Only the first is absolute.\n"
    "- HARD LEGALITY: you may build AT MOST ONE item from each mutex group given. Those "
    "items cannot be equipped together in-game, so breaking this makes the build "
    "impossible rather than merely bad. Never put two from one group in a build.\n"
    "- HARD LEGALITY: at most ONE ACTIVE item per build. Items with an activatable effect "
    "(Zhonya's Stasis, Gargoyle Stoneplate, Locket, Shurelya's, Redemption, Mikael's, "
    "Stridebreaker, Goredrinker, Galeforce, Hextech Rocketbelt, Mercurial) are mutually "
    "exclusive; a build may hold only one. Never return two active items.\n"
    "- REDUNDANCY: some combinations are legal and normally wasteful (listed below the "
    "mutex groups where they apply). Build two from such a group only when you say why "
    "the overlap earns its gold.\n"
    "- DEFAULT STRATEGY: preferences you may override with an explicit argument.\n"
    "- REACTIVE ITEMS (Maw, Serpent's Fang, anti-heal items...) answer a specific enemy "
    "comp. These builds are written with no enemy team in view, so they belong in "
    "situational swaps ONLY, never the core build.\n"
    "- GUARDIAN ANGEL is NOT merely reactive: at 3200g it carries real Attack Damage and "
    "Armor, so it is a legitimate LATE purchase for a diver or engage champion who "
    "converts a revive into a second engage, or who carries a large shutdown worth "
    "protecting. It may enter a core build only at position 4 or 5, and only with an "
    "explicit reason. Never give it a guaranteed slot: if the only argument is that it is "
    "a good item, buy damage or uptime instead.\n"
    "- SCORE EACH COMPLETE BUILD after selecting its items, boots and runes. "
    "Use 0-100 where 50 is playable/average, 70 is strong, 85 is exceptional and 95+ "
    "is near-perfect. Score overall, burst, sustainedDamage, survivability, mobility, "
    "utility, earlyPower and confidence; ground the verdict in the champion's kit, build "
    "timing and requested variant.\n"
    "- Wild Rift rune page = 1 keystone + 3 minors from ONE tree + 1 flex from a DIFFERENT tree (the flex must NOT be in the primary tree; a page runs two trees). "
    "SLOTS: the 3 tree minors must come one from each of the tree's 3 slots (shown in "
    "the pool) -- two minors from the same slot is ILLEGAL. The flex is not slot-tied. "
    "Read the rune EFFECTS given and pick for synergy, not popularity. Do NOT fall back "
    "on one habitual flex rune: pick the flex that serves THIS build's job.\n"
    "- You may ONLY use items and runes from the provided pools (exact slug/name). "
    "Never invent.\n"
    "- UNKNOWN ENEMY TEAM: these builds are chosen without knowing the enemy draft, so "
    "they must stay broadly useful. Do not invent enemy champions or threats; do not "
    "assume heavy healing, shields, tanks, crit, magic or physical damage, CC or poke. "
    "Prefer items with reliable value across common drafts and frequently-activated effects "
    "over conditional ceilings. The first three purchases must form a coherent, broadly "
    "functional core. Keep narrow reactive answers (dedicated anti-heal, anti-shield, "
    "matchup-specific defence) in situational, never the trusted core, UNLESS the item has "
    "broad non-reactive value on its own. Lower confidence relative to a known matchup.\n"
    "- TIE-BREAKERS when two items or builds are close, in order: 1) earlier practical power "
    "spike; 2) stronger interaction with the champion's core combat pattern; 3) greater "
    "usefulness across common drafts; 4) better completion timing at similar value; 5) less "
    "reliance on a rare activation or perfect execution; 6) better role and variant fit; "
    "7) better preservation of the champion's required combat uptime; 8) higher rubric score. "
    "Do NOT let a numeric score overrule stronger strategic reasoning when scores are close.\n"
    "- Be decisive: the BEST option per variant, not a menu."
)


def _load(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _norm(s: str) -> str:
    """Collapse whitespace without clipping any source mechanic or tooltip."""
    return " ".join((s or "").split())


def _item_pool(items: list[dict]) -> str:
    by_cat: dict[str, list[str]] = {}
    for it in items:
        categories = set(it.get("categories") or [])
        if categories & {"Basic", "MidTier"}:
            continue
        stats = ", ".join(f"{k} {v['value']}{'%' if v['percent'] else ''}"
                          for k, v in it["stats"].items()) or "no stats"
        # Full passive text: clipping can hide the mechanic that decides whether
        # an item actually synergizes with the champion.
        passive = _norm(" ".join(it["passives"])) or "(no passive)"
        by_cat.setdefault(it["category"], []).append(
            f'  {it["slug"]} | {it["name"]} | {it["cost"]}g | {stats} | {passive}')
    order = ["Physical", "Magic", "Defense", "Support", "Active", "Boots"]
    return "\n".join(f"[{c}]\n" + "\n".join(by_cat[c]) for c in order if c in by_cat)


def _rune_pool(runes: list[dict]) -> str:
    """Keystones + minors WITH their FULL effect text and SLOT numbers, so the
    model can reason about synergies AND respect the one-minor-per-slot rule.
    No clipping: stack counts, conditions, and conversions must remain intact."""
    ks = [f'  {r["name"]}: {_norm(r.get("description", ""))}'
          for r in runes if r["type"] == "Keystone"]
    by_tree_slot: dict[str, dict[int, list[str]]] = {}
    for r in runes:
        if r["type"] == "Minor":
            slot = SLOT_OF.get(r["name"], 0)
            by_tree_slot.setdefault(r.get("tree", "?"), {}).setdefault(slot, []).append(
                f'    {r["name"]}: {_norm(r.get("description", ""))}')
    blocks = []
    for t, slots in by_tree_slot.items():
        lines = [f"[{t}]"]
        for s in sorted(slots):
            lines.append(f"  slot {s}:" if s else "  (unslotted):")
            lines += slots[s]
        blocks.append("\n".join(lines))
    return ("Keystones:\n" + "\n".join(ks)
            + "\nMinor runes by tree and SLOT (pick ONE minor from each of the "
              "primary tree's 3 slots; the flex minor may be any minor from any tree):\n"
            + "\n".join(blocks))


def hard_exclusive_groups(rules: dict) -> dict[str, list[str]]:
    """Groups the game will not let you equip two of.

    data/item_rules.json used to hold these under `mutexGroups` as a plain
    name -> [slugs] map. It now splits true legality (`hardExclusive`) from
    merely-wasteful overlap (`redundancyGroups`), and each group carries its
    evidence. The old key is still read so an older copy of the data file
    degrades to the previous behaviour rather than silently enforcing nothing --
    which is exactly what happened when the file was restructured.
    """
    groups: dict[str, list[str]] = {}
    for name, group in (rules.get("hardExclusive") or {}).items():
        if name.startswith("_"):
            continue
        if isinstance(group, dict) and group.get("slugs"):
            groups[name] = list(group["slugs"])
        elif isinstance(group, list):
            groups[name] = list(group)
    for name, slugs in (rules.get("mutexGroups") or {}).items():
        groups.setdefault(name, list(slugs))
    return groups


def _mutex_block(rules: dict, items_by_slug: dict) -> str:
    def label(slugs):
        return ", ".join(items_by_slug[s]["name"] for s in slugs if s in items_by_slug)

    lines = ["HARD EXCLUSIVITY (cannot be equipped together in-game; build at most ONE "
             "from each group):"]
    for name, slugs in hard_exclusive_groups(rules).items():
        lines.append(f"  {name}: {label(slugs)}")

    redundancy = {n: g for n, g in (rules.get("redundancyGroups") or {}).items()
                  if not n.startswith("_") and isinstance(g, dict)}
    if redundancy:
        lines.append("")
        lines.append("REDUNDANCY (legal, normally a waste; two from a group needs a reason):")
        for name, group in redundancy.items():
            lines.append(f"  {name}: {label(group.get('slugs') or [])}")
            lines.append(f"    why it is usually wrong: {group.get('why', '')}")
    return "\n".join(lines)


def _champion_block(c: dict, champ_class: str, role: str) -> str:
    bs = c.get("baseStats", {})
    def lvl(k):
        s = bs.get(k)
        # base -> lvl15 with the explicit per-level growth, so the model can
        # reason about scaling (a champion with huge HP/level needs less bought HP)
        return f"{s['base']}->{s['lvl15']} (+{s['perLevel']}/lvl)" if s else "?"
    stat_line = (f"HP {lvl('hp')}, AD {lvl('ad')}, AS {lvl('attackSpeed')}, "
                 f"Armor {lvl('armor')}, MR {lvl('mr')}, MS {bs.get('moveSpeed',{}).get('base','?')}")
    # Full ability text; conversions and conditional mechanics often occur near
    # the end of long ability descriptions.
    # Ability text is normalised first: the scrape leaves at least one malformed
    # formula (Hecarim's Warpath arrives as "gains 0 = (12% bonus MS)"), and the
    # model should not be asked to infer a number from a broken one.
    abils = "\n".join(f"  [{a['slot']}] {a['name']}: {a['text']}"
                      for a in advisor_profiles.normalized_abilities(c["name"]))

    # The raw `scalesWith` and `mechanics` lists are not sent any more. They are
    # produced by substring matching and are close to constant across the roster
    # (`onHit` on 85 of 141 champions, `ap` on 117), so they told the model
    # almost nothing while reading as fact. The derived profiles replace them.
    derived = advisor_profiles.profile(c["name"])
    lines = [
        f"CHAMPION: {c['name']}  (class {champ_class}, role {role})",
        f"Base stats (lvl1->lvl15): {stat_line}",
        f"Primary damage: {c.get('primaryDamage')}",
        "COMBAT PROFILE (derived from this kit's ability text, cooldowns and ratios): "
        + json.dumps(derived["combatProfile"]),
        "SCALING PROFILE (share of this kit's ratio weight, cooldown-adjusted): "
        + json.dumps(derived.get("scalingProfile", {})),
        "BUILD IDENTITY PROFILE (AUTHORITATIVE for itemisation and every variant): "
        + json.dumps(derived["buildIdentityProfile"]),
    ]
    if derived.get("buildPathViability"):
        lines.append(
            "BUILD-PATH VIABILITY (OVERRIDES the raw ratio share): "
            + json.dumps(derived["buildPathViability"])
            + '. "core" can anchor a build; "secondary" may add to an item\'s value but '
            'cannot justify it alone; "not_viable" must not drive item choices. A large raw '
            "ratio does NOT authorise a build path. A reviewed alternativePath is the only "
            "exception, and applies to Alternative Path only.")
    for note in derived.get("scalingNotes", []):
        lines.append(f"  note: {note}")
    if derived.get("structuredEffects"):
        lines.append("STRUCTURED EFFECTS (machine-parsed; where these disagree with the "
                     "ability prose below, TRUST THESE): "
                     + json.dumps(derived["structuredEffects"]))
    if derived.get("abilityTextArtifacts"):
        lines.append("DATA QUALITY WARNING: some ability text below is malformed. Do not "
                     "infer a number from it. " + " | ".join(derived["abilityTextArtifacts"]))
    lines.append(f"Abilities:\n{abils}")
    return "\n".join(lines)


def _kit_hints(c: dict) -> list[str]:
    """Deterministic synergy hooks detected from ability text. These are injected
    as mandatory considerations so the model can't overlook a conversion mechanic
    (an LLM pass sometimes did, e.g. Hecarim's move-speed -> AD passive)."""
    abilities = c.get("abilities", [])
    texts = {a["slot"]: " ".join((a.get("text") or "").lower().split()) for a in abilities}
    full = " ".join(texts.values())
    hints: list[str] = []

    # Move speed converts to damage (Hecarim Warpath style).
    for slot, t in texts.items():
        if re.search(r"\(\s*\d+(\.\d+)?%\s*bonus (ms|movement speed)\s*\)", t) or \
           re.search(r"(attack damage|\bad\b|damage)[^.]{0,60}equal to[^.]{0,60}bonus (movement speed|ms)", t) or \
           re.search(r"bonus (movement speed|ms)[^.]{0,60}(as|into|converted to)[^.]{0,30}(attack damage|\bad\b)", t):
            hints.append(
                f"MOVE SPEED HAS OFFENSIVE VALUE: ability [{slot}] converts bonus move speed into "
                "damage. Move-speed sources (Phase Rush, Nimbus Cloak, Celerity, Ghost, MS item "
                "passives) are worth MORE here than for an ordinary champion, so weigh them more "
                "favourably -- but select them only when their complete package beats the "
                "alternatives. Do NOT force a variant to be built around move speed.")
            break

    # Energy user: mana items are dead stats.
    is_energy = "energy" in full
    if is_energy:
        hints.append("ENERGY USER: this champion has no mana. Mana items and mana runes are useless.")

    # Short-cooldown spam kit -> compounding per-cast engines.
    def _min_cd(a) -> float | None:
        vals = []
        for cd in a.get("cooldowns") or []:
            for tok in re.split(r"[/\s]+", str(cd)):
                try:
                    vals.append(float(tok))
                except ValueError:
                    pass
        return min(vals) if vals else None
    spam = [(a["slot"], _min_cd(a)) for a in abilities
            if a["slot"] in ("1", "2", "3") and _min_cd(a) is not None and _min_cd(a) <= 4.5]
    if spam and not is_energy:
        slot, cd = spam[0]
        hints.append(
            f"SHORT-CD SPAM KIT: ability [{slot}] recharges every ~{cd:g}s. Per-cast engines compound "
            "hard here: Manamune/Muramana, Spear of Shojin, spellblade items, ability haste. Mana "
            "economy is a real constraint -- evaluate this engine explicitly.")

    # % max-health damage (tank shred already in kit).
    if re.search(r"(target'?s?|enemy'?s?|their) (maximum|max)(imum)? (health|hp)", full):
        hints.append("BUILT-IN %MAX-HP DAMAGE: the kit already shreds high-HP targets; attack speed / "
                     "haste multiply it, and anti-tank items are less needed.")
    # Scales with own max health.
    elif re.search(r"(his|her|your|its) (maximum|max)(imum)? (health|hp)", full):
        hints.append("OWN MAX-HP SCALING: abilities scale with the champion's own max health, so HP "
                     "items are damage items too (Heartsteel-style stacking is premium).")

    # Attack pattern, from the derived profile rather than the `onHit` tag.
    #
    # The tag fired for 85 of 141 champions because it matches the literal words
    # "next attack" -- so Hecarim, whose E reads "if his next attack is within 5
    # seconds", was told that "attack speed and on-hit items multiply the
    # passive". That is the opposite of true for him, and it is the single
    # wrongest sentence this prompt used to contain. The profile separates
    # applying an on-hit effect ONCE from relying on applying it repeatedly.
    combat = advisor_profiles.combat_profile(c["name"])
    if combat["repeatedOnHitReliance"] in ("medium", "high"):
        hints.append(
            f"REPEATED ON-HIT KIT (reliance: {combat['repeatedOnHitReliance']}): damage depends "
            "on landing on-hit effects over and over, so attack speed and on-hit items "
            "multiply the kit rather than merely adding to it.")
    elif combat["spellbladeProcReliability"] == "high":
        hints.append(
            "ABILITY-WEAVING KIT: it empowers or follows up single attacks between casts, so "
            "SPELLBLADE items pay off. This is NOT an on-hit stacking kit: attack speed and "
            "repeated-application items (Guinsoo's, Runaan's, Nashor's, Terminus) do far less "
            "here than their item text suggests, because the effect lands once per rotation.")
    if combat["critValue"] == "none":
        hints.append("NO CRIT PATTERN: the kit cannot convert critical strike chance into "
                     "meaningful damage; treat crit items as dead stats.")
    # No move-speed hint here: the ability-text scan above already emits a more
    # specific one naming the exact slot, and two hints saying the same thing
    # reads as two separate findings.

    return hints


THREATS = ["vs Tanks", "vs AP", "vs AD", "vs Healing", "vs Shields", "vs CC", "vs Crit", "vs Poke"]


def _schema(variants: list[str]) -> str:
    build_shape = (
        '{"summary":"1-2 sentences","coreBuild":[{"slug":"...","reason":"<=14 words"}],'
        ' "boots":{"slug":"...","reason":"..."},'
        ' "situationalBoots":[{"boots":"<tier-2 slug>","when":"specific matchup condition"}],'
        ' "buildScore":{"overall":0-100,"burst":0-100,"sustainedDamage":0-100,'
        '"survivability":0-100,"mobility":0-100,"utility":0-100,"earlyPower":0-100,'
        '"confidence":0-100,"reason":"short evidence-based verdict"},'
        ' "situational":[{"slug":"...","vs":"one of ' + "|".join(THREATS) + '",'
        '"replaces":"<coreBuild slug this swaps out>","atPosition":1-5}],'
        ' "situationalRunes":[{"name":"...","vs":"e.g. vs Assassins|vs Tanks|vs Poke",'
        '"replaces":"<rune name in the page, or a coreBuild item slug>",'
        '"replacesType":"rune|item"}],'
        ' "runes":{"keystone":{"name":"...","reason":"..."},'
        '"primaryTree":"Domination|Resolve|Precision|Sorcery",'
        '"treeMinors":[{"name":"...","reason":"<=10 words"}],'
        '"flexMinor":{"name":"...","reason":"<=10 words"}}}')
    vlines = "\n".join(f'    "{v}": {build_shape}   // {VARIANT_DESC[v]}' for v in variants)
    return (
        "The trusted variants (Standard / Aggressive / Durable) are three EMPHASES of the "
        "SAME legitimate core build, not three deliberately different builds. Do NOT change "
        "an item solely to make one variant look different from another: shared first items, "
        "a shared two-item core, shared boots and shared runes are EXPECTED when they remain "
        "optimal. A variant should differ only where its objective makes a different choice "
        "strategically better. Alternative Path, when present, must implement the exact "
        "approved alternativePath from the BUILD IDENTITY PROFILE; it is never free-form novelty.\n"
        "coreBuild = 5 items IN BUILD ORDER (index 0 rushed first). treeMinors = exactly 3 "
        "from primaryTree; flexMinor = 1 from any tree. situational = 0 TO 4 MEANINGFUL swaps "
        "covering DISTINCT threats (vs Tanks / vs AP / vs Healing / vs Shields / vs CC ...), "
        "each naming the coreBuild slug it replaces and the purchase position that item holds "
        "(atPosition 1-5). Return an EMPTY list when no strong adaptation exists -- do NOT "
        "invent filler swaps to fill the list. Do not put every swap on the last item: answer "
        "each threat at the position where it actually matters, usually the 2nd or 3rd purchase. "
        "A situational rune must NOT already be on the main rune page -- swapping in a rune "
        "you are already running is meaningless. "
        "situationalBoots = 0 TO 2 tier-2 boot alternatives with a specific condition. For "
        "Bruisers, Fighters, Marksmen and Assassins, put Plated Steelcaps (vs repeated AD/basic "
        "attacks) and Mercury's Treads (vs AP/CC) here rather than using them as unconditional "
        "main boots. Do not repeat the main boot. "
        "situationalRunes may either swap a rune on the page (replacesType 'rune') or "
        "cover an item's job so the item is no longer needed (replacesType 'item', e.g. a "
        "tenacity rune instead of a tenacity item).\n"
        "Return ONLY this JSON object (synergyNotes FIRST -- the builds must follow from them):\n{\n"
        '  "synergyNotes": ["2-4 short bullets: the kit\'s strongest passive/ability <-> '
        'item/rune interactions"],\n'
        '  "damageProfile": "short label e.g. lethality / crit-adc / ap-bruiser / tank",\n'
        '  "canOneshot": true/false,\n'
        '  "builds": {\n' + vlines + "\n  }\n}")


def build_prompt(cblock, item_pool, rune_pool, mutex_block, variants, role,
                 kit_flags: list[str] | None = None) -> str:
    role_hint = ROLE_RUNE_HINTS.get(role, "")
    hint = f"\nROLE NOTE: {role_hint}\n" if role_hint else ""
    flags = ""
    if kit_flags:
        flags = ("\nKIT FLAGS (auto-detected from the ability text -- you MUST address each one "
                 "in synergyNotes and reflect it in the builds where it fits):\n"
                 + "\n".join(f"- {f}" for f in kit_flags) + "\n")
    vlist = ", ".join(f"{v} ({VARIANT_DESC[v]})" for v in variants)
    return (f"{cblock}\n{hint}{flags}\nDesign these build variants: {vlist}\n\n"
            f"=== ITEM POOL (exact slugs only) ===\n{item_pool}\n\n{mutex_block}\n\n"
            f"=== RUNE POOL (exact names only, effects shown) ===\n{rune_pool}\n\n"
            f"{_schema(variants)}")


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON object in output")
    return json.loads(m.group(0))


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


# Variants whose core items must match the champion's ability scaling.
DAMAGE_VARIANTS = {"damage", "burst", "oneshot", "crit", "poke", "battlemage"}


DEFENSIVE_BOOTS = {"mercurys-treads", "plated-steelcaps"}
OFFENSE_FIRST_CLASSES = {"Bruiser", "Fighter", "Marksman", "Assassin"}

# tier-3 boot slug -> the tier-2 it upgrades from, so a model that names the
# finished boot can be mapped back to the one you actually buy at 10:00.
_T3_TO_T2: dict[str, str] = {
    it["upgradesTo"]: it["slug"]
    for it in (json.loads(ITEMS.read_text(encoding="utf-8")) if ITEMS.exists() else [])
    if it.get("category") == "Boots" and it.get("upgradesTo")
}


def _item_path_signals(core: list[dict], item_by_slug: dict[str, dict]) -> dict[str, int]:
    """Count itemisation signals used by the build-identity gate.

    Categories answer broad path questions (Physical vs Magic vs Defense), while
    explicit stats answer narrower reviewed rules such as "no AP items". Hidden
    passive value is included for on-hit, but this deliberately does not pretend
    to score item power -- it only detects a clearly wrong build path.
    """
    signals = {
        "physical": 0, "magic": 0, "defense": 0, "AP": 0, "AD": 0,
        "crit": 0, "attackSpeed": 0, "onHit": 0, "lethality": 0,
    }
    for entry in core:
        item = item_by_slug.get(entry.get("slug")) or {}
        categories = set(item.get("categories") or []) | {item.get("category")}
        stats = item.get("stats") or {}
        if "Physical" in categories:
            signals["physical"] += 1
        if "Magic" in categories:
            signals["magic"] += 1
        if "Defense" in categories:
            signals["defense"] += 1
        if stats.get("ap"):
            signals["AP"] += 1
        if stats.get("ad") or "Physical" in categories:
            signals["AD"] += 1
        if stats.get("crit"):
            signals["crit"] += 1
        if stats.get("attackSpeed"):
            signals["attackSpeed"] += 1
        passive_text = " ".join(str(x) for x in (item.get("passives") or []))
        if "onHit" in (item.get("tags") or []) or re.search(r"on[- ]hit", passive_text, re.I):
            signals["onHit"] += 1
        if "lethality" in (item.get("tags") or []):
            signals["lethality"] += 1
    return signals


def _path_errors(label: str, core: list[dict], item_by_slug: dict[str, dict],
                 identity: dict) -> list[str]:
    """Hard-gate every variant against the authoritative build identity."""
    errors: list[str] = []
    signals = _item_path_signals(core, item_by_slug)
    approved = identity.get("approvedBuildPaths") or []

    if label == "offmeta":
        alternative = identity.get("alternativePath")
        if not isinstance(alternative, dict) or not alternative.get("id"):
            return [f"{label}: no reviewed alternativePath exists; omit this variant"]
        anchors = list(alternative.get("anchorStats") or [])
        for anchor in anchors:
            key = str(anchor)
            canonical = {"ad": "AD", "ap": "AP", "defence": "defense"}.get(
                key.lower(), key)
            minimum = 2
            if canonical in ("AD", "AP") and len(anchors) == 1:
                minimum = 3
            if signals.get(canonical, 0) < minimum:
                errors.append(
                    f"{label}: approved Alternative Path '{alternative.get('label')}' needs "
                    f"at least {minimum} {canonical}-supporting items; found "
                    f"{signals.get(canonical, 0)}"
                )
        if {str(a).upper() for a in anchors} >= {"AD", "AP"} and (
                signals["AD"] + signals["AP"] < 3):
            errors.append(f"{label}: hybrid Alternative Path needs at least 3 combined AD/AP items")
        return errors

    if not approved:
        errors.append(f"{label}: champion has no approvedBuildPaths in its identity profile")
        return errors

    primary = identity.get("primaryBuildPath")
    if primary == "physical" and signals["magic"] >= 2 and signals["magic"] > signals["physical"]:
        errors.append(
            f"{label}: build leaves approved physical paths {approved}: "
            f"{signals['magic']} Magic vs {signals['physical']} Physical items"
        )
    elif primary == "magic" and signals["physical"] >= 2 and signals["physical"] > signals["magic"]:
        errors.append(
            f"{label}: build leaves approved magic paths {approved}: "
            f"{signals['physical']} Physical vs {signals['magic']} Magic items"
        )
    elif primary == "tank" and signals["defense"] < 2:
        errors.append(
            f"{label}: build leaves approved tank paths {approved}: only "
            f"{signals['defense']} defensive items"
        )
    elif primary == "support" and signals["physical"] >= 3:
        errors.append(
            f"{label}: build leaves approved support paths {approved}: "
            f"{signals['physical']} Physical items"
        )

    rules = {}
    variant_rules = identity.get("variantRules") or {}
    rules.update(variant_rules.get("*") or {})
    rules.update(variant_rules.get(label) or {})
    checks = (
        ("minimumDefensiveItems", "defense", lambda actual, expected: actual < expected,
         "defensive items", "at least"),
        ("minimumPhysicalOrDefenseItems", "physical_or_defense",
         lambda actual, expected: actual < expected, "Physical/Defense items", "at least"),
        ("maximumAPItems", "AP", lambda actual, expected: actual > expected,
         "AP items", "at most"),
        ("maximumADItems", "AD", lambda actual, expected: actual > expected,
         "AD items", "at most"),
        ("minimumAttackSpeedItems", "attackSpeed", lambda actual, expected: actual < expected,
         "attack-speed items", "at least"),
        ("minimumOnHitItems", "onHit", lambda actual, expected: actual < expected,
         "on-hit items", "at least"),
        ("minimumCritItems", "crit", lambda actual, expected: actual < expected,
         "crit items", "at least"),
        ("maximumLethalityItems", "lethality", lambda actual, expected: actual > expected,
         "lethality items", "at most"),
    )
    for rule, signal, fails, noun, comparator in checks:
        if rule not in rules:
            continue
        expected = int(rules[rule])
        actual = (len({c["slug"] for c in core if
                       (item_by_slug.get(c["slug"], {}).get("category") in ("Physical", "Defense"))})
                  if signal == "physical_or_defense" else signals[signal])
        if fails(actual, expected):
            errors.append(
                f"{label}: build identity requires {comparator} {expected} {noun}; found {actual}"
            )
    return errors


def _validate(rec, variants, item_by_slug, rune_by_name, mutex,
              scales: list[str] | None = None, role: str = "",
              champ_class: str = "",
              name: str = "") -> tuple[dict, list[str], list[str]]:
    """Validate + normalise one champion record.

    Returns (clean, errors, warnings). `errors` are hard failures that make a
    build unshippable (illegal / incomplete / contradicts the champion's
    scalings) and trigger a repair round-trip; `warnings` are issues we
    tolerate but persist for auditing.
    """
    err: list[str] = []
    warn: list[str] = []
    scales = scales or []
    identity = advisor_profiles.build_identity_profile(name) if name else {}
    item_canon = {_canon(s): it for s, it in item_by_slug.items()}
    item_canon.update({_canon(it["name"]): it for it in item_by_slug.values()})
    rune_canon = {_canon(n): r for n, r in rune_by_name.items()}

    def ok_item(slug, label, cat=None, forbid=("Boots", "Enchantment")):
        it = item_by_slug.get(slug) or item_canon.get(_canon(slug))
        if not it:
            err.append(f"{label}: unknown item '{slug}'")
            return None
        if cat and it["category"] != cat:
            err.append(f"{label}: {it['slug']} is category {it['category']}, expected {cat}")
        if not cat and it["category"] in forbid:
            err.append(f"{label}: {it['slug']} is {it['category']} -- not allowed in this slot")
        return {"slug": it["slug"], "name": it["name"], "cost": it["cost"], "icon": it["icon"]}

    def ok_rune(name):
        return rune_by_name.get(name) or rune_canon.get(_canon(name))

    def rune_entry(e, label, want_type="Minor"):
        r = ok_rune(e.get("name"))
        if not r:
            err.append(f"{label}: unknown rune '{e.get('name')}'")
            return None
        if r.get("type") != want_type:
            err.append(f"{label}: {r['name']} is a {r.get('type')}, expected {want_type}")
        return {"name": r["name"], "slug": r["slug"], "tree": r.get("tree", ""),
                "icon": r["icon"], "reason": e.get("reason", "")}

    def val_build(bd, label):
        build_error_start = len(err)
        bd = bd or {}
        core = []
        for e in bd.get("coreBuild") or []:
            b = ok_item(e.get("slug"), f"{label} core")
            if b:
                b["reason"] = e.get("reason", "")
                core.append(b)
        slugs = [c["slug"] for c in core]
        for s in slugs:
            if s in SITUATIONAL_ONLY:
                err.append(f"{label}: {s} is a reactive/situational item -- move it to "
                           f"situational swaps, never the core build")
        # Late-strategic items (Guardian Angel) are allowed, but not early and
        # not silently. They used to be banned outright via SITUATIONAL_ONLY,
        # which was wrong: at 3200g it carries real AD and Armor, so it is a
        # genuine late purchase for a diver rather than an answer to a comp.
        for late_slug, cfg in LATE_STRATEGIC.items():
            if late_slug not in slugs:
                continue
            position = slugs.index(late_slug) + 1
            minimum = int(cfg.get("minPosition", 4))
            if position < minimum:
                err.append(f"{label}: {late_slug} is a late strategic purchase and cannot sit "
                           f"at position {position}; it may enter the build at position "
                           f"{minimum} or later, and needs an explicit reason")
        if len(core) != 5:
            err.append(f"{label}: coreBuild has {len(core)} valid items, need exactly 5")
        if len(set(slugs)) != len(slugs):
            err.append(f"{label}: duplicate item in coreBuild")
        for gname, group in mutex.items():
            hit = sorted(set(slugs) & set(group))
            if len(hit) > 1:
                err.append(f"{label}: ILLEGAL -- {' + '.join(hit)} share mutex group '{gname}'")
        # Only ONE active item per build (Bard's durable build was returning
        # Stasis + a second active). Same rule the live advisor enforces.
        active_hit = sorted(s for s in slugs if s in advisor_itemmeta.ACTIVE_ITEMS)
        if len(active_hit) > 1:
            err.append(f"{label}: ILLEGAL -- {' + '.join(active_hit)} are all active items; "
                       "a build may contain at most ONE active item")

        # Every build, including Standard and Durable, is checked against the
        # champion's main combat engine and approved paths. The old gate ran on
        # DAMAGE_VARIANTS only and trusted the coarse `scalesWith` substrings,
        # which is how full AP Nasus/Rammus and AP Fiora/Irelia escaped.
        if core and identity:
            err.extend(_path_errors(label, core, item_by_slug, identity))

        boots_in = bd.get("boots") or {}
        boots = ok_item(boots_in.get("slug"), f"{label} boots", cat="Boots") if boots_in.get("slug") else None
        if boots:
            boots["reason"] = boots_in.get("reason", "")
            # Defensive boots are not main boots for damage classes -- they trade
            # away the kill pressure the build exists for. Matches the live
            # advisor's rule so both generators agree.
            if champ_class in OFFENSE_FIRST_CLASSES and boots["slug"] in DEFENSIVE_BOOTS:
                err.append(f"{label}: {boots['slug']} is a defensive boot; a {champ_class} must not "
                           "wear it as main boots -- pick offensive/utility boots and offer this as a "
                           "situational swap instead")
        else:
            err.append(f"{label}: missing boots")

        # Boot timing, derived rather than asked for. Patch 7.2 unlocks the
        # tier-3 upgrade at 10:00, so a build wears the tier-2 first and upgrades
        # a couple of items later. The live advisor returns both halves; the
        # curated generator only ever returned one, so recommended builds showed
        # boots dumped at the end of the order with no timing while generated
        # builds showed "T2 ... T3 @10:00". The tier-2 the model picked plus the
        # item data's upgradesTo is all that is needed to close the gap.
        boots_early = None
        boots_upgrade_after = None
        if boots:
            # The prompt asks for the TIER-2 boot, but the model sometimes names
            # the tier-3 directly (armorcrusher-boots rather than
            # boots-of-dynamism). That is a naming slip, not a bad build choice,
            # so resolve it back to its tier-2 parent instead of spending a
            # repair round on it -- the pair is what carries the 10:00 timing.
            trimmed = {k: boots[k] for k in ("slug", "name", "cost", "icon")}
            parent_slug = _T3_TO_T2.get(boots["slug"])
            if parent_slug and (parent := item_by_slug.get(parent_slug)):
                boots = {"slug": parent["slug"], "name": parent["name"],
                         "cost": parent["cost"], "icon": parent["icon"],
                         "reason": boots.get("reason", "")}
            else:
                boots = {**trimmed, "reason": boots.get("reason", "")}
            # ok_item() trims the record to slug/name/cost/icon, so the upgrade
            # path has to come from the source item data, not from `boots`.
            source_boot = item_by_slug.get(boots["slug"]) or {}
            upgrade_slug = source_boot.get("upgradesTo")
            upgrade_src = item_by_slug.get(upgrade_slug) if upgrade_slug else None
            upgrade = ({"slug": upgrade_src["slug"], "name": upgrade_src["name"],
                        "cost": upgrade_src["cost"], "icon": upgrade_src["icon"]}
                       if upgrade_src else None)
            if upgrade:
                boots_early = dict(boots)          # the tier 2 you buy first
                boots = dict(upgrade)              # the tier 3 you finish on
                boots["reason"] = boots_early.get("reason", "")
                # Matches the live generator's convention (see enemy-build.tsx):
                # the upgrade lands around the second completed item.
                boots_upgrade_after = 2

        # Optional matchup boots use the same tier-2 -> tier-3 contract as the
        # live advisor. This field was requested in the prompt for years but was
        # absent from the curated schema, so every defensive alternative was
        # silently discarded.
        situational_boots = []
        seen_situational_boots = set()
        main_t2_slug = (boots_early or boots or {}).get("slug")
        for entry in bd.get("situationalBoots") or []:
            if not isinstance(entry, dict):
                err.append(f"{label}: situationalBoots entries must be objects")
                continue
            requested = entry.get("boots") or entry.get("slug")
            candidate = ok_item(requested, f"{label} situational boots", cat="Boots")
            if not candidate:
                continue
            tier2_slug = _T3_TO_T2.get(candidate["slug"], candidate["slug"])
            source = item_by_slug.get(tier2_slug) or {}
            if not source.get("upgradesTo"):
                err.append(f"{label}: situationalBoots must use a tier-2 boot, got {requested}")
                continue
            if tier2_slug == main_t2_slug or tier2_slug in seen_situational_boots:
                continue
            when = str(entry.get("when") or entry.get("vs") or "").strip()
            if not when:
                err.append(f"{label}: situational boot {tier2_slug} needs a specific condition")
                continue
            if champ_class in OFFENSE_FIRST_CLASSES and tier2_slug not in DEFENSIVE_BOOTS:
                err.append(f"{label}: a {champ_class}'s situational boots must be defensive "
                           f"matchup choices; got {tier2_slug}")
                continue
            seen_situational_boots.add(tier2_slug)
            situational_boots.append({
                "boots": tier2_slug,
                "bootsUpgrade": source.get("upgradesTo"),
                "when": when,
            })
        if len(situational_boots) > 2:
            err.append(f"{label}: situationalBoots has {len(situational_boots)} choices; maximum is 2")
            situational_boots = situational_boots[:2]
        if champ_class in OFFENSE_FIRST_CLASSES and not situational_boots:
            warn.append(f"{label}: no defensive situationalBoots supplied for {champ_class}")
        # Boot enchantments no longer exist. Patch 7.2 dissolved them into
        # class-restricted ACTIVE items and tier-3 boots ("active effects are now
        # tied to champion classes"), so data/items.json has zero Enchantment
        # items and this slot is unsatisfiable: it failed every champion with
        # "missing boot enchantment". The actives it used to cover (Locket,
        # Stasis, Quicksilver, Protobelt) are ordinary items in the pool now.
        # Kept as an always-null field because the frontend already renders it
        # conditionally (BuildItem | null).
        ench = None
        situ = []
        core_slugs_now = list(slugs)
        for e in bd.get("situational") or []:
            b = ok_item(e.get("slug"), f"{label} situational", forbid=())
            if not b:
                continue
            vs = e.get("vs") or e.get("when") or ""
            if vs and not vs.lower().startswith("vs"):
                vs = f"vs {vs}"
            b["when"] = vs
            rep = e.get("replaces")
            rep_it = (item_by_slug.get(rep) or item_canon.get(_canon(rep))) if rep else None
            if not rep_it or rep_it["slug"] not in core_slugs_now:
                # A swap that does not name a real core item has no timing and no
                # meaning, so it is dropped rather than shipped half-formed.
                warn.append(f"{label}: dropped situational {b['slug']} -- replaces "
                            f"'{rep}' which is not in the core build")
                continue
            b["replaces"] = rep_it["slug"]
            # Position follows from what it replaces; the model's own atPosition
            # is only a cross-check.
            b["atPosition"] = core_slugs_now.index(rep_it["slug"]) + 1
            situ.append(b)
        # 0-4 meaningful swaps: an empty list is valid (no strong adaptation),
        # and more than 4 is filler. Only flag the over-full case now.
        if len(situ) > 4:
            warn.append(f"{label}: {len(situ)} situational swaps is filler; keep the 4 that "
                        "answer real threats")
        if situ and all(s["atPosition"] >= 4 for s in situ):
            warn.append(f"{label}: every situational swap lands on item 4-5, too late to "
                        "matter in a 15-20 minute game")

        # Summoner spells are assigned, not generated. The choice is a lookup
        # (jungler takes Smite, enchanter support takes Heal, a run-down
        # champion takes Ghost), so asking the model for it only created a way
        # for an otherwise good build to fail validation. Shared with the live
        # advisor so both generators produce the same spells.
        sums, summoner_reason = advisor_summoners.resolved(name, role, champ_class)
        for entry in sums:
            entry["reason"] = summoner_reason

        rin = bd.get("runes") or {}
        ks_in = rin.get("keystone") or {}
        ks = ok_rune(ks_in.get("name"))
        if not ks:
            err.append(f"{label}: unknown/missing keystone '{ks_in.get('name')}'")
        elif ks.get("type") != "Keystone":
            err.append(f"{label}: {ks['name']} is not a keystone")
        primary = rin.get("primaryTree", "")
        if primary not in ("Domination", "Resolve", "Precision", "Sorcery"):
            err.append(f"{label}: bad primaryTree '{primary}'")
        tmins = [x for x in (rune_entry(e, f"{label} minors") for e in rin.get("treeMinors") or []) if x]
        if len(tmins) != 3:
            err.append(f"{label}: {len(tmins)} valid tree minors, need exactly 3")
        if len({t["name"] for t in tmins}) != len(tmins):
            err.append(f"{label}: duplicate tree minor")
        for tm in tmins:
            if primary and tm["tree"] != primary:
                err.append(f"{label}: minor {tm['name']} is {tm['tree']}, not {primary}")
        # slot legality: exactly one minor from each of the tree's 3 slots
        slots = sorted(SLOT_OF.get(t["name"], 0) for t in tmins)
        if len(tmins) == 3 and slots != [1, 2, 3]:
            named = ", ".join(f"{t['name']}(slot {SLOT_OF.get(t['name'], '?')})" for t in tmins)
            err.append(f"{label}: tree minors must be one per slot 1/2/3 -- got {named}")
        flex = rune_entry(rin.get("flexMinor") or {}, f"{label} flex") if (rin.get("flexMinor") or {}).get("name") else None
        if not flex:
            err.append(f"{label}: missing flex minor")
        elif flex["name"] in {t["name"] for t in tmins}:
            err.append(f"{label}: flex minor duplicates a tree minor ({flex['name']})")

        # situational rune swaps (vs Assassins / vs Tanks / ...), validated names
        page_names = {t["name"] for t in tmins} | ({flex["name"]} if flex else set()) \
            | ({ks["name"]} if ks else set())
        situ_runes = []
        for e in bd.get("situationalRunes") or []:
            r = ok_rune(e.get("name"))
            if not r:
                warn.append(f"{label}: unknown situational rune '{e.get('name')}'")
                continue
            # A rune already on the main page cannot also be the thing you swap
            # IN. The model produced "take Legend: Tenacity over Overgrowth vs
            # CC" on a page that already ran Legend: Tenacity, which reads as
            # nonsense to anyone following the build. Drop it rather than repair:
            # the main page is the stronger statement and stays as-is.
            if r["name"] in page_names:
                warn.append(f"{label}: dropped situational rune {r['name']} -- it is already on "
                            "the main rune page, so swapping it in means nothing")
                continue
            entry = {"name": r["name"], "slug": r["slug"], "icon": r["icon"],
                     "when": e.get("vs") or e.get("when") or ""}
            rep = e.get("replaces")
            # Two legal shapes: swapping another rune on the page, or covering an
            # item's job well enough that the item can leave the build (a
            # tenacity rune instead of a tenacity item, say).
            rep_rune = ok_rune(rep) if rep else None
            rep_item = (item_by_slug.get(rep) or item_canon.get(_canon(rep))) if rep else None
            if e.get("replacesType") == "item" and rep_item and rep_item["slug"] in core_slugs_now:
                entry["replaces"] = rep_item["slug"]
                entry["replacesType"] = "item"
                entry["replacesLabel"] = rep_item["name"]
            elif rep_rune and rep_rune["name"] in page_names:
                entry["replaces"] = rep_rune["name"]
                entry["replacesType"] = "rune"
                entry["replacesLabel"] = rep_rune["name"]
            elif rep:
                warn.append(f"{label}: situational rune {r['name']} replaces '{rep}', "
                            "which is neither a rune on the page nor a core item")
            situ_runes.append(entry)

        build_score = bd.get("buildScore") or {}
        score_keys = ("overall", "burst", "sustainedDamage", "survivability",
                      "mobility", "utility", "earlyPower", "confidence")
        clean_score = {}
        if not isinstance(build_score, dict):
            err.append(f"{label}: buildScore must be an object")
        else:
            for key in score_keys:
                try:
                    value = float(build_score.get(key))
                except (TypeError, ValueError):
                    err.append(f"{label}: buildScore.{key} must be numeric")
                    continue
                if not 0 <= value <= 100:
                    err.append(f"{label}: buildScore.{key} must be between 0 and 100")
                else:
                    clean_score[key] = round(value, 1)
            reason = str(build_score.get("reason") or "").strip()
            if not reason:
                err.append(f"{label}: buildScore.reason is required")
            clean_score["reason"] = reason
        result = {
            "summary": bd.get("summary", ""),
            # User-facing name and trust tier for this variant. The stored key is
            # still the legacy id (standard/damage/tanky/offmeta); these are what
            # the frontend can show and badge without a data migration.
            "label": VARIANT_LABEL.get(label, label.title()),
            "trustTier": VARIANT_TRUST_TIER.get(label, "trusted"),
            "buildScore": clean_score,
            "coreBuild": core, "boots": boots, "enchantment": ench, "situational": situ,
            "bootsEarly": boots_early, "bootsUpgradeAfter": boots_upgrade_after,
            "situationalBoots": situational_boots,
            "situationalRunes": situ_runes,
            "summoners": sums,
            "runes": {
                "keystone": ({"name": ks["name"], "slug": ks["slug"], "icon": ks["icon"],
                              "reason": ks_in.get("reason", "")} if ks else None),
                "primaryTree": primary, "treeMinors": tmins, "flexMinor": flex,
            },
        }
        if identity:
            if label == "offmeta" and identity.get("alternativePath"):
                result["pathLabel"] = identity["alternativePath"].get(
                    "label", "Alternative Path")
                # Only newly validated, mechanically approved alternatives get
                # this marker. Legacy Experimental records never acquire it by
                # being relabelled in the frontend.
                if len(err) == build_error_start:
                    result["alternativePathApproved"] = True
            else:
                approved = identity.get("approvedBuildPaths") or []
                primary_label = approved[0] if approved else identity.get("primaryBuildPath", "")
                if primary_label:
                    result["pathLabel"] = str(primary_label).replace("-", " ").title()
        return result

    builds_in = rec.get("builds") or {}
    out_builds = {}
    for v in variants:
        if v not in builds_in:
            err.append(f"missing variant: {v}")
            continue
        out_builds[v] = val_build(builds_in[v], v)
    notes = [str(n) for n in (rec.get("synergyNotes") or []) if str(n).strip()]
    if not notes:
        warn.append("no synergyNotes")
    return {
        "synergyNotes": notes,
        "damageProfile": rec.get("damageProfile", ""),
        "canOneshot": bool(rec.get("canOneshot", False)),
        "variants": variants,
        "builds": out_builds,
    }, err, warn


REPAIR_ATTEMPTS = 2


class LLM:
    """Thin provider wrapper: deepseek / gemini (cloud) or ollama (local)."""

    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        if provider == "gemini":
            from google import genai
            from google.genai import errors as genai_errors
            from google.genai import types
            self._types = types
            self._errors = genai_errors
            self._client = genai.Client()
        elif provider == "deepseek":
            # Shared with the live advisor: reads the environment first, then
            # web-next/.env.local. A terminal run inherits nothing from Next.js,
            # so without the fallback this failed with the key sitting in the repo.
            self._key = advisor_env.api_key()
            if not self._key:
                raise SystemExit(advisor_env.missing_key_message())

    def generate(self, parts: list[str], temperature: float, system: str | None = None) -> str:
        system = system or SYSTEM
        if self.provider == "deepseek":
            # OpenAI-compatible chat completions with JSON mode.
            body = {
                "model": self.model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": "\n\n".join(parts)}],
                "response_format": {"type": "json_object"},
                "thinking": {"type": "enabled"},
                "reasoning_effort": "high",
                "temperature": temperature,
                "max_tokens": DEEPSEEK_MAX_OUTPUT_TOKENS,
                "stream": False,
            }
            headers = {"Authorization": f"Bearer {self._key}"}
            for attempt in range(5):
                try:
                    r = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=300)
                    if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                        wait = 3 * (attempt + 1)
                        print(f"    ... deepseek {r.status_code}, retry in {wait}s")
                        time.sleep(wait)
                        continue
                    if not r.ok:  # 4xx is permanent: surface the body, don't retry
                        raise RuntimeError(f"deepseek {r.status_code}: {r.text}")
                    choice = r.json()["choices"][0]
                    if choice.get("finish_reason") == "length":
                        raise RuntimeError(
                            "deepseek output reached max_tokens; refusing truncated JSON")
                    return choice["message"]["content"] or ""
                except requests.RequestException as e:
                    if attempt < 4:
                        print(f"    ... deepseek error ({e}), retry in 5s")
                        time.sleep(5)
                        continue
                    raise
            return ""
        if self.provider == "gemini":
            config = self._types.GenerateContentConfig(
                system_instruction=system, response_mime_type="application/json",
                temperature=temperature)
            for attempt in range(5):
                try:
                    resp = self._client.models.generate_content(
                        model=self.model, contents=parts, config=config)
                    return resp.text or ""
                except (self._errors.ServerError, self._errors.ClientError) as e:
                    code = getattr(e, "code", None)
                    if code in (429, 500, 502, 503, 504) and attempt < 4:
                        wait = 3 * (attempt + 1)
                        print(f"    ... {code}, retry in {wait}s")
                        time.sleep(wait)
                        continue
                    raise
            return ""
        # ollama: single user message, JSON mode. num_ctx must cover our ~14K-token
        # prompt -- ollama's default (2048) silently truncates otherwise.
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": "\n\n".join(parts)}],
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": 16384},
        }
        for attempt in range(3):
            try:
                r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=900)
                r.raise_for_status()
                return r.json().get("message", {}).get("content", "")
            except requests.RequestException as e:
                if attempt < 2:
                    print(f"    ... ollama error ({e}), retry in 5s")
                    time.sleep(5)
                    continue
                raise
        return ""


JUDGE_SYSTEM = (
    "You are a ruthless Wild Rift build reviewer. You are given a champion's kit, "
    "deterministic KIT FLAGS, and several candidate build sets from theorycrafters. "
    "Per variant, pick the candidate whose build best exploits the kit's synergies "
    "(flags addressed, compounding engines, legal choices; validation errors listed "
    "count heavily against a candidate). Judge the BUILD QUALITY, not the prose."
)


def _judge_prompt(cblock: str, kit_flags: list[str], variants: list[str],
                  cands: list[dict]) -> str:
    flags = "\n".join(f"- {f}" for f in kit_flags) or "(none)"
    blocks = []
    for i, c in enumerate(cands):
        errs = "; ".join(c["err"]) or "none"
        blocks.append(f"--- CANDIDATE {i} (validation errors: {errs}) ---\n"
                      + json.dumps(c["raw"], ensure_ascii=False))
    return (f"{cblock}\n\nKIT FLAGS:\n{flags}\n\n"
            + "\n\n".join(blocks)
            + "\n\nPick the best candidate PER VARIANT and the best synergyNotes. "
            + "Judge every variant on how well it delivers what that variant is for, "
            + "not on raw strength: for 'offmeta', reject any candidate that leaves the "
            + "exact approved alternativePath in the BUILD IDENTITY PROFILE. Do not reward "
            + "novelty or a single incidental ratio. "
            + "Return ONLY this JSON object:\n"
            + '{"picks": {' + ", ".join(f'"{v}": <candidate index>' for v in variants)
            + '}, "synergyFrom": <candidate index>, '
            + '"why": {' + ", ".join(f'"{v}": "<=15 words"' for v in variants) + "}}")


def _assemble(cands: list[dict], picks: dict, synergy_from: int, variants: list[str]) -> dict:
    """Merge the judge's per-variant picks into one raw record."""
    n = len(cands)
    src = cands[synergy_from if 0 <= synergy_from < n else 0]["raw"]
    merged = {
        "synergyNotes": src.get("synergyNotes") or [],
        "damageProfile": src.get("damageProfile", ""),
        "canOneshot": sum(bool(c["raw"].get("canOneshot")) for c in cands) * 2 > n,
        "builds": {},
    }
    for v in variants:
        idx = picks.get(v)
        idx = idx if isinstance(idx, int) and 0 <= idx < n else 0
        chosen = cands[idx]["raw"].get("builds", {}).get(v)
        if chosen is None:  # fall back to any candidate that has the variant
            for c in cands:
                if v in c["raw"].get("builds", {}):
                    chosen = c["raw"]["builds"][v]
                    break
        merged["builds"][v] = chosen or {}
    return merged


def _repair_prompt(raw: dict, errors: list[str]) -> str:
    return (
        "Your previous build JSON has validation errors. Fix EVERY error and return the "
        "FULL corrected JSON in the exact same schema (all variants, not just the broken "
        "parts). Keep everything that was already valid.\n\nERRORS:\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\nPREVIOUS JSON:\n" + json.dumps(raw, ensure_ascii=False)
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--provider", choices=("deepseek", "gemini", "ollama"), default="deepseek")
    ap.add_argument("--model", default="", help="defaults per provider")
    # Candidate count defaults from CURATED_CANDIDATE_COUNT so a deployment can
    # raise generation quality (more candidates + judge) without a code change;
    # --best-of still overrides it.
    _default_best_of = int(os.environ.get("CURATED_CANDIDATE_COUNT", "1") or "1")
    ap.add_argument("--best-of", type=int, default=_default_best_of,
                    help="generate N candidates and judge-pick the best per variant "
                         "(default from CURATED_CANDIDATE_COUNT env, else 1)")
    ap.add_argument("--validate-only", action="store_true",
                    help="re-audit data/champion_builds.json offline, no API calls")
    args = ap.parse_args()
    args.model = args.model or DEFAULT_MODELS[args.provider]

    items = _load(ITEMS)
    runes = _load(RUNES)
    champs = _load(CHAMPS)
    # Transform forms author their own builds: a permanently transformed Rhaast
    # is a bruiser, and blue Kayn's item set does not fit him.
    champs = champs + [f for c in champs for f in (c.get("forms") or [])]
    verified = (_load(CHAMPION_OVERRIDES) or {}).get("champions", {})
    for champion in champs:
        override = verified.get(champion.get("name"), {})
        for stat, values in override.get("baseStats", {}).items():
            champion.setdefault("baseStats", {})[stat] = {
                key: value for key, value in values.items()
                if key in {"base", "perLevel", "lvl15"}
            }
    rules = _load(RULES) or {}
    site = {c["name"]: c for c in (_load(SITE) or {}).get("champions", [])}
    item_by_slug = {it["slug"]: it for it in items}
    rune_by_name = {r["name"]: r for r in runes}
    mutex = {k: set(v) for k, v in hard_exclusive_groups(rules).items()}
    item_pool, rune_pool = _item_pool(items), _rune_pool(runes)
    mutex_block = _mutex_block(rules, item_by_slug)

    def class_role(name: str) -> tuple[str, str]:
        meta = site.get(name)
        if meta:
            return meta.get("class", ""), meta.get("role", "")
        return CLASS_FALLBACK.get(name, ("", ""))

    scales_by_name = {c["name"]: c.get("scalesWith") or [] for c in champs}

    if args.validate_only:
        cache = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
        bad = 0
        for name, rec in sorted(cache.items()):
            _, err, warn = _validate(rec, rec.get("variants") or [], item_by_slug,
                                     rune_by_name, mutex, scales_by_name.get(name),
                                     rec.get("role", ""), rec.get("class", ""), name)
            if err or warn:
                bad += 1 if err else 0
                print(f"  {name}: " + "; ".join(err + [f"(warn) {w}" for w in warn]))
        print(f"\n{len(cache)} champions audited, {bad} with hard errors")
        return

    only = {n.strip() for n in args.only.split(",") if n.strip()}
    if only:
        champs = [c for c in champs if c["name"] in only]

    cache: dict[str, dict] = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [c for c in champs if only or c["name"] not in cache]
    print(f"{len(champs)} in scope | {len(todo)} to build | {args.provider}:{args.model} "
          f"| best-of {args.best_of}")

    llm = LLM(args.provider, args.model)

    unresolved: list[str] = []
    for i, c in enumerate(todo, 1):
        name = c["name"]
        champ_class, role = class_role(name)
        variants = variants_for(name, champ_class, role)
        cblock = _champion_block(c, champ_class or "?", role or "?")
        kit_flags = _kit_hints(c)
        prompt = build_prompt(cblock, item_pool, rune_pool, mutex_block, variants, role, kit_flags)

        def _validated(text):
            raw = _extract_json(text)
            clean, err, warn = _validate(raw, variants, item_by_slug, rune_by_name,
                                         mutex, c.get("scalesWith"), role, champ_class, name)
            return raw, clean, err, warn

        # A single generation is deterministic. Best-of remains intentionally
        # diverse, while judge and repair are low-temperature adjudication steps.
        cands = []
        n = max(1, args.best_of)
        for k in range(n):
            temp = 0.0 if n == 1 else 0.35
            try:
                raw, clean, err, warn = _validated(llm.generate([prompt], temp))
                cands.append({"raw": raw, "clean": clean, "err": err, "warn": warn})
            except Exception as e:  # noqa: BLE001
                print(f"    candidate {k}: parse failed ({e})")
        if not cands:
            print(f"  ! {name}: all candidates failed -- skipping")
            unresolved.append(name)
            continue

        if len(cands) > 1:
            # Judge pass picks the best build per variant across candidates.
            # Preferred judge: the deterministic fight engine (kill speed x
            # survivability at the 15-min gold reality). LLM judge is the
            # fallback for champions without extracted formulas.
            picks: dict = {}
            if True:  # LLM judge is the only active judge
                try:
                    verdict = _extract_json(llm.generate(
                        [_judge_prompt(cblock, kit_flags, variants, cands)], 0.0, JUDGE_SYSTEM))
                    raw = _assemble(cands, verdict.get("picks") or {},
                                    verdict.get("synergyFrom", 0), variants)
                except Exception as e:  # noqa: BLE001
                    print(f"    judge failed ({e}) -- falling back to cleanest candidate")
                    raw = min(cands, key=lambda x: len(x["err"]))["raw"]
            clean, err, warn = _validate(raw, variants, item_by_slug, rune_by_name,
                                         mutex, c.get("scalesWith"), role, champ_class, name)
        else:
            raw, clean, err, warn = (cands[0]["raw"], cands[0]["clean"],
                                     cands[0]["err"], cands[0]["warn"])

        # Repair loop: hand the errors back and ask for a corrected full JSON.
        rounds = 0
        while err and rounds < REPAIR_ATTEMPTS:
            rounds += 1
            print(f"    repair {rounds}/{REPAIR_ATTEMPTS}: {len(err)} errors -- {err}")
            try:
                text = llm.generate([prompt, _repair_prompt(raw, err)], 0.0)
                raw = _extract_json(text)
            except Exception as e:  # noqa: BLE001 -- network hiccup / unparseable
                print(f"    repair aborted ({e}) -- shipping best-so-far")
                break
            clean, err, warn = _validate(raw, variants, item_by_slug, rune_by_name,
                                         mutex, c.get("scalesWith"), role, champ_class, name)

        clean["name"] = name
        clean["class"] = champ_class
        clean["role"] = role
        if err:
            clean["errors"] = err  # shipped ONLY for auditing; frontend must skip these
            unresolved.append(name)
        if warn:
            clean["warnings"] = warn
        cache[name] = clean
        payload = json.dumps(cache, ensure_ascii=False, indent=2)
        OUT.write_text(payload, encoding="utf-8")
        WEB_OUT.write_text(payload, encoding="utf-8")  # keep the frontend copy in sync
        # ASCII only: the default Windows console codepage (cp1252) raises
        # UnicodeEncodeError on symbols, which would crash the run *after* the
        # builds were already written.
        flag = f"  [{len(err)} errors]" if err else (f"  [{len(warn)} warnings]" if warn else "")
        print(f"  [{i}/{len(todo)}] {name} [{champ_class}/{role}]: {'/'.join(variants)}{flag}")

    print(f"\nwrote {OUT.relative_to(ROOT)} + {WEB_OUT.relative_to(ROOT)} ({len(cache)} champions)")
    if unresolved:
        print(f"UNRESOLVED after repair ({len(unresolved)}): {', '.join(unresolved)}")


if __name__ == "__main__":
    main()
