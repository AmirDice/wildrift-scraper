"""Engine-driven build search: the "absolute best build" loop.

For each champion variant, instead of trusting the LLM's 5-item pick:

  1. The LLM proposes a POOL of ~14 candidate items for the variant (it's good
     at shortlisting synergies; slugs are validated against the item data).
  2. The fight engine exhaustively scores EVERY legal 5-item combination from
     that pool (mutex rules enforced), at the 15-min gold reality + full build,
     with the champion's kit-adjusted offense/defense weights.
  3. The winning combo replaces the build's coreBuild, greedily ordered by
     marginal mid-game value (what you rush actually matters).
  4. CORE items = items appearing in >=60% of the top-20 combos: the picks the
     search says the build cannot do without (2-3, badge-flagged).
  5. One LLM pass writes short reasons for the chosen items.

Runes/boots/enchant/summoners stay from the generated record (searching those
dimensions is a later step). Requires extracted formulas (data/ability_formulas
.json) — champions without them are skipped.

Run (needs DEEPSEEK_API_KEY):
    python -m scripts.search_builds --only "Hecarim"
    python -m scripts.search_builds
"""
from __future__ import annotations

import argparse
import json
import os
import re
from itertools import combinations
from pathlib import Path

from scripts.build_champions_llm import (LLM, SLOT_OF, _champion_block, _extract_json,
                                         _kit_hints)
from web.fight_engine import (FORMULAS, ITEMS, PREFIX_LEVELS, RUNE_ENGINE, RUNE_FX,
                              _build_lists, attack_profile, build_curve, score_items,
                              stat_usability)

ROOT = Path(__file__).resolve().parent.parent
BUILDS = ROOT / "data" / "champion_builds.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "builds.json"
RULES = json.loads((ROOT / "data" / "item_rules.json").read_text(encoding="utf-8"))
MUTEX = [set(g) for g in RULES.get("mutexGroups", {}).values()]
RUNES_ALL = json.loads((ROOT / "data" / "runes.json").read_text(encoding="utf-8"))
_ARCH_PATH = ROOT / "data" / "champion_archetypes.json"
ARCHETYPES = (json.loads(_ARCH_PATH.read_text(encoding="utf-8"))
              if _ARCH_PATH.exists() else {})
# How each archetype itemizes. Fed to the shortlist LLM: the stat probe cannot
# see RHYTHM (a weaver's kit spacing casts to the 1.5s Spellblade cooldown), so
# without this tag Hecarim's shortlist never favoured Trinity-class items.
ARCH_GUIDE = {
    "spellcaster": "SPELL-CASTER: abilities carry the damage, autos are filler. "
                   "Prioritise ability haste, penetration and raw AD/AP (Shojin / "
                   "Luden's class). Avoid attack-speed and on-hit items.",
    "autoattacker": "AUTO-ATTACKER: damage rides continuous basic attacks. "
                    "Prioritise attack speed, crit and on-hit (BotRK / Terminus / "
                    "IE class). Haste items are secondary.",
    "weaver": "WEAVER: the kit's loop is cast -> auto -> cast, naturally matching "
              "the 1.5s Spellblade cooldown. SPELLBLADE ITEMS ARE CORE: include "
              "at least TWO of Trinity Force / Divine Sunderer / Lich Bane / "
              "Iceborn Gauntlet in the shortlist.",
    "onhitcaster": "ON-HIT CASTER: this kit's ABILITIES apply on-hit effects, so "
                   "on-hit items trigger from spells. Favour on-hit items in the "
                   "champion's scaling stat (Nashor's class for AP).",
}
RUNE_BY_NAME = {r["name"]: r for r in RUNES_ALL}
RUNE_SLOTS = json.loads((ROOT / "data" / "rune_slots.json").read_text(encoding="utf-8"))["trees"]
# Reactive anti-comp items (GA, Maw, anti-heal...) never compete for main-build
# slots — they live in situational swaps only.
SITUATIONAL_ONLY = set((RULES.get("situationalOnly") or {}).get("slugs") or [])
CHAMPS = {c["name"]: c for c in json.loads(
    (ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))}

POOL_SIZE = 14
TOP_K = 20
CORE_FREQ = 0.6

# Variant identity constraints. Items fall into three classes:
#   TANK    = pure defensive items (wildriftfire's Defense category)
#   BRUISER = damage + survivability hybrids (Sterak's, Death's Dance, ...)
#   damage  = everything else
# Per variant: (tank_min, tank_max, defensive_min, defensive_max) where
# "defensive" counts tank AND bruiser items. Tuned so damage variants stay full
# damage (one bruiser item of padding allowed, never a tank item), balanced is
# never glass but never tanky, and tanky runs 2-3 tank items — full 4-5 tank is
# reserved for actual Tank-class champions.
# (tank_min, tank_max, defensive_min, defensive_max). is_defensive INCLUDES
# tanks, so a defensive minimum of 2 is satisfiable by 2 tank items, 2 hybrids,
# or one of each -- "2 from either" needs no extra rule.
IDENTITY_BOUNDS = {
    # Standard is UNBOUNDED, deliberately. It means "the best all-around build
    # for this champion", so a forced tank/defensive count would override the
    # very score that defines it. Defense is already priced: standard weights
    # EHP at 40% (VARIANT_WEIGHTS), stat_weights floors HP at 0.8 and armour/MR
    # at 0.75 on every champion, and kit_adjust shifts the split per kit. If a
    # build comes out with no defensive item, that is the model's answer, not a
    # gap to paper over.
    # The bounds BELOW are different in kind: they define what a variant MEANS
    # (a "oneshot" that wants 3 tank items is not a oneshot), so they stay.
    "standard": (0, 5, 0, 5),
    # Aggressive variants are allowed to be genuinely all-in: no floor.
    "oneshot": (0, 0, 0, 1), "burst": (0, 0, 0, 1), "crit": (0, 0, 0, 1),
    "poke": (0, 0, 0, 1), "damage": (0, 0, 0, 1), "dps": (0, 0, 0, 1),
    "antitank": (0, 0, 0, 1), "sustained": (0, 1, 0, 2),
    "balanced": (0, 1, 1, 2), "battlemage": (0, 1, 0, 2),
    "survivability": (0, 3, 2, 4), "tanky": (2, 3, 3, 4), "utility": (0, 2, 0, 3),
}
# "tanky" bounds for Tank-CLASS champions, by role.
#   Support: a tank support's job is to absorb and peel, so 4-5 defensive is
#     fine -- damage is not what it is there to provide.
#   Jungle / Baron: a solo-lane or jungle tank still has to threaten something.
#     Capping defensive at 4 of 5 forces at least ONE slot of damage (Sunfire,
#     Titanic, Heartsteel-style tank-damage all count as tank items too, so this
#     is satisfiable without giving up durability), so the build is not a body
#     with no damage.
TANKY_FULL_TANK = (3, 5, 4, 5)
TANKY_SOLO_TANK = (3, 4, 3, 4)

# "standard" caps, per CLASS. Standard is meant to be the best all-around build
# and would ideally be unbounded -- but the score cannot currently be trusted to
# decide the mix, so these are a deliberate counterweight, not a measurement.
#
# WHY: fight_score is additive (w_off*off + w_def*deff) and EHP is linear in HP,
# which costs 2.67 gold/point against AD's 35. So per gold, defense really does
# buy more score, and nothing in the model punishes dealing no damage. Measuring
# defensive weights honestly (instead of the 0.8/0.75 floors) made it WORSE --
# HP came out the best stat on every champion, Ziggs included. Left alone,
# Graves' "standard" came out Divine Sunderer / Sunfire / Sterak's / Black
# Cleaver / Shojin: a tank build on a marksman.
#
# Remove these once fight_score is multiplicative (kill them before they kill
# you) rather than a weighted sum.
#   Marksman: at most ONE defensive/bruiser item, full stop.
#   Bruiser/Fighter: at most ONE true tank item; bruiser hybrids uncapped, since
#     resist-hybrids (Death's Dance, Sterak's) ARE the archetype's core.
STANDARD_BY_CLASS = {
    "Marksman": (0, 1, 0, 1),
    "Bruiser": (0, 1, 0, 5),
    "Fighter": (0, 1, 0, 5),
    # Mages drift tank exactly like marksmen (Ziggs came out with a tank core
    # and ~15k EHP): same additive-objective root cause, same counterweight.
    "Mage": (0, 1, 0, 1),
    "Assassin": (0, 1, 0, 1),
}


# A variant that names a damage TYPE has to actually deliver it. The identity
# bounds only ever constrained tank/defensive counts, so "crit" was just
# "damage" with a different label: Graves' crit build came out
# Dominik's/Youmuu's/Edge of Night/Chempunk/Death's Dance -- a lethality build
# with ZERO crit items. Crit is also the one stat with a real breakpoint: it is
# worthless in ones and twos and compounds with Infinity Edge, so half-measures
# are worse than not going crit at all.
# 4 of 5, not 3. A floor of 3 was satisfied while the two spare slots filled
# with lethality (Graves' crit build came out Youmuu's + Duskblade + 3 crit),
# which is the complaint the constraint exists to answer: a crit build that is
# 40% lethality is not a crit build. 4 leaves exactly one flex slot, and with 12
# crit items in the pool it stays satisfiable.
CRIT_MIN = {"crit": 4}


def is_crit(slug: str) -> bool:
    return "crit" in ((ITEMS.get(slug) or {}).get("stats") or {})


def is_ap_champion(name: str) -> bool:
    """A kit whose damage is magic. Read from the extracted formulas, not class:
    Gwen and Malphite are not 'Mages' but both deal magic damage."""
    rec = FORMULAS.get(name) or {}
    champ = CHAMPS.get(name) or {}
    return (rec.get("primaryDamage") or champ.get("primaryDamage")) == "magic"


def is_ad_champion(name: str) -> bool:
    rec = FORMULAS.get(name) or {}
    champ = CHAMPS.get(name) or {}
    return (rec.get("primaryDamage") or champ.get("primaryDamage")) == "physical"


def _is_ad_item(slug: str) -> bool:
    """An AD carry item: gives attack damage and no ability power.

    Hybrids that give BOTH (or neither, like Nashor's / Lich Bane / Riftmaker)
    are not barred -- plenty of AP bruisers want those. This only stops the
    Divine Sunderer / Sundered Sky / Bloodthirster class of pick.
    """
    stats = (ITEMS.get(slug) or {}).get("stats") or {}
    return "ad" in stats and "ap" not in stats


def _is_ap_item(slug: str) -> bool:
    """The mirror of _is_ad_item: ability power and no attack damage. The AD->AP
    lock existed without this reverse, which is how Pantheon (a lethality
    assassin) was handed Infinity Orb by the polish pass."""
    stats = (ITEMS.get(slug) or {}).get("stats") or {}
    return "ap" in stats and "ad" not in stats


# Nashor's Tooth is the one attack-speed item AP carries genuinely build: its
# Gnaw on-hit carries a 30% AP ratio in the tooltip, so it scales WITH the AP
# the build is stacking. Guinsoo's adaptive grant looks identical in the stat
# line (both give "25 AD or 50 AP"), but its on-hit is flat + crit-scaled, i.e.
# dead weight for an AP build. The fx vocabulary cannot yet express "on-hit AP
# ratio", so this distinction is not derivable from data -- a named exception
# with the reason recorded beats silently barring both.
AP_AS_EXCEPTIONS = {"nashors-tooth"}

# Per the user's judgment: Divine Sunderer is a bruiser/tank-shredder sustain
# item and has no place on burst assassins (it was landing in Viego's standard
# AND oneshot). Not derivable from the sim -- its %maxHP spellblade genuinely
# scores well on anyone who weaves autos -- so it is an explicit rule.
ASSASSIN_BARRED = {"divine-sunderer"}


def item_allowed(slug: str, name: str, champ_class: str, role: str) -> bool:
    """Champion-fit rules shared by the LLM-shortlist filter AND the polish
    pass. They must agree: the polish searches the full item pool, so any rule
    enforced only at the shortlist quietly leaks back in through polish (that is
    exactly how Ambessa got Locket and Viego got Divine Sunderer)."""
    it = ITEMS.get(slug) or {}
    stats = it.get("stats") or {}
    # Support items are for supports. Locket/Redemption/Mikael's price their
    # value in ally effects the engine only credits on support builds; on a
    # Baron bruiser they are a dead slot.
    if it.get("category") == "Support" and role != "Support":
        return False
    if champ_class == "Assassin" and slug in ASSASSIN_BARRED:
        return False
    if is_ap_champion(name) and champ_class not in ("Tank", "Enchanter"):
        if _is_ad_item(slug):
            return False
        # Defensive picks must be tanky-AP (Zhonya's, Banshee's), not pure tank:
        # an AP champion's defensive slot still has to serve the build.
        if is_defensive(slug) and "ap" not in stats:
            return False
        # Attack-speed items likewise must bring AP (Nashor's), not be generic
        # on-hit sticks (Guinsoo's) -- Gwen scales with AP, not with adaptive.
        if "attackSpeed" in stats and "ap" not in stats and slug not in AP_AS_EXCEPTIONS:
            return False
    if is_ad_champion(name) and _is_ap_item(slug):
        return False
    return True


def is_tank(slug: str) -> bool:
    return (ITEMS.get(slug) or {}).get("category") == "Defense"


def is_defensive(slug: str) -> bool:
    """Tank items plus bruiser survivability hybrids. Pure damage items with a
    token HP line (Trinity) still count if they carry resists; pure-HP+damage
    bruiser items (Sterak's) count; HP-with-offense engines (Shojin) don't."""
    if is_tank(slug):
        return True
    stats = (ITEMS.get(slug) or {}).get("stats") or {}
    if "armor" in stats or "mr" in stats:  # resist hybrids like Death's Dance
        return True
    offensive = any(k in stats for k in ("ad", "ap", "attackSpeed", "crit"))
    return "hp" in stats and not offensive  # pure-HP items (Sterak's-style)

POOL_SYSTEM = (
    "You are a Wild Rift theorycrafter. Given a champion and ONE build variant, "
    "shortlist the candidate items a search engine should consider. Include every "
    "item a strong player might argue for: the obvious core, the synergy picks "
    "(read the kit flags!), and 2-3 defensive/hybrid options even for damage "
    "variants. Use ONLY slugs from the provided pool. No boots, no enchants.\n"
    "THE VARIANT IS A CONTRACT. If it names a damage type, the shortlist must be "
    "able to deliver it: for a CRIT variant include AT LEAST 7 items that actually "
    "grant Critical Rate, because the build must run 4 of 5 crit items to reach the "
    "breakpoint where Infinity Edge compounds. Lethality items (Youmuu's, Duskblade, "
    "Edge of Night, Serylda's) do NOT belong in a crit shortlist -- lethality and crit "
    "are different builds, and mixing them gives you neither.\n"
    "For a TANKY variant on an AP champion (magic damage kit), shortlist TANKY-AP "
    "items -- Zhonya's Hourglass, Banshee's Veil, Rod of Ages, Riftmaker, Seraph's "
    "Embrace -- NOT pure resist items: tank items without AP are invalid on AP "
    "champions and get rejected, which empties the pool entirely.\n"
    "For a TANKY variant, do NOT shortlist only pure resist items. A solo-lane or "
    "jungle tank still has to threaten something, so include 3-4 tank items that DEAL "
    "damage or scale off HP (Sunfire Aegis, Titanic Hydra, Heartsteel, Dead Man's "
    "Plate, Unending Despair) -- an all-resist shortlist leaves the build a body with "
    "no damage.\n"
    'Return ONLY JSON: {"pool": ["slug", ...]} with exactly the requested count.'
)

REASON_SYSTEM = (
    "You write terse Wild Rift item justifications. For each item in each variant "
    "of the given champion build, write a reason under 13 words grounded in the "
    "champion's kit. Return ONLY JSON: "
    '{"<variant>": {"<slug>": "reason", ...}, ...}'
)


def _canon(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


ITEM_CANON = {_canon(s): s for s in ITEMS}
ITEM_CANON.update({_canon(it["name"]): s for s, it in ITEMS.items()})


def legal(combo: tuple[str, ...]) -> bool:
    s = set(combo)
    return all(len(s & g) <= 1 for g in MUTEX)


def propose_pool(llm: LLM, champ: dict, champ_class: str, role: str,
                 variant: str, current: list[str]) -> list[str]:
    """LLM shortlist, seeded with the current build's items, validated."""
    pool_txt = "\n".join(
        f"  {s} | {it['name']} | {it['cost']}g | " +
        (" ".join(it["passives"])[:650] or "no passive")
        for s, it in ITEMS.items()
        if it["category"] not in ("Boots", "Enchantment") and s not in SITUATIONAL_ONLY)
    flags = "\n".join(f"- {f}" for f in _kit_hints(champ))
    prof = attack_profile(champ["name"], current)
    style_line = (f"ATTACK STYLE (engine-measured): {prof['style']} — "
                  f"build around {prof['buildHint']}.")
    u = stat_usability(champ["name"])
    usable = [s for s in ("ad", "ap", "attackSpeed", "crit") if u.get(s, 0) >= 0.5]
    wasted = [s for s in ("ad", "ap", "attackSpeed", "crit") if u.get(s, 0) < 0.5]
    scaling_line = (f"USABLE OFFENSE (from kit scaling, not class): uses {', '.join(usable) or 'none'}; "
                    f"wastes {', '.join(wasted) or 'none'}. Do not shortlist items whose main offensive "
                    f"stat is wasted (their damage stat is dead weight); prefer usable-offense, ability "
                    f"haste, HP and resist items. Class does not restrict items — kit scaling does.")
    arch = (ARCHETYPES.get(champ["name"]) or {}).get("archetype")
    arch_line = ""
    if arch and arch in ARCH_GUIDE:
        reason = (ARCHETYPES[champ["name"]].get("reason") or "")[:120]
        arch_line = f"ARCHETYPE: {ARCH_GUIDE[arch]}" + (f" ({reason})" if reason else "") + "\n"
    prompt = (f"{_champion_block(champ, champ_class, role)}\n\nKIT FLAGS:\n{flags}\n\n"
              f"{arch_line}{style_line}\n{scaling_line}\n\n"
              f"VARIANT: {variant}\nCurrent build (keep these in the pool): {current}\n\n"
              f"ITEM POOL:\n{pool_txt}\n\n"
              f"Shortlist exactly {POOL_SIZE} slugs.")
    raw = _extract_json(llm.generate([prompt], 0.3, POOL_SYSTEM))
    no_resource = any(m.get("kind") == "noResource"
                      for m in FORMULAS.get(champ["name"], {}).get("mechanics") or [])

    def ok(slug: str) -> bool:
        if slug not in ITEMS or ITEMS[slug]["category"] in ("Boots", "Enchantment"):
            return False
        if slug in SITUATIONAL_ONLY:
            return False
        if no_resource and "mana" in (ITEMS[slug].get("stats") or {}):
            return False  # mana items are dead stats on energy/rage kits
        return item_allowed(slug, champ["name"], champ_class, role)

    out: list[str] = []
    for s in raw.get("pool") or []:
        slug = ITEM_CANON.get(_canon(str(s)))
        if slug and ok(slug) and slug not in out:
            out.append(slug)
    for s in current:  # never drop what the generator picked (unless situational-only)
        if ok(s) and s not in out:
            out.append(s)
    # BACKFILL: the champion-fit rules can gut an LLM shortlist (an AP champion's
    # "tanky" list is mostly pure-resist items, all barred), and a pool under 6
    # used to silently SKIP the variant, leaving a stale build in place -- that
    # is how Gwen/tanky survived two runs unchanged. Top up deterministically
    # with every allowed finished item; a bigger pool only costs combos, and the
    # search scores them all anyway.
    if len(out) < 10:
        fill = sorted((s for s in ITEMS if ok(s) and s not in out),
                      key=lambda s: (-int(ITEMS[s].get("cost") or 0)))
        out.extend(fill[:POOL_SIZE - len(out)])
    return out[:POOL_SIZE + 3]


EARLY_LEVEL = 11  # ordering basis: value while the game is still early-mid


# When the tier-3 boot upgrade lands, as a COUNT OF ITEMS BOUGHT BEFORE IT.
#
# This is a game rule, not something the optimizer derives, and the distinction
# matters. 7.2 unlocks tier 3 at 10:00, which is about two items in. You buy it
# then because it is unlocked and costs ~1000g of change ALONGSIDE saving for
# the next item -- not INSTEAD of one. Our model has no gold clock: it scores
# discrete purchases, so it can only ask "is 1000g of boots a bigger spike than
# a 3400g item", and for a carry the answer is always no, which parked the
# upgrade last. Encoding the unlock is honest; pretending to optimise it is not.
# A real gold clock (purchases when affordable) would derive this, and would
# also give "ahead vs behind" timing for free.
BOOTS_UPGRADE_AFTER = 2


def boots_options() -> list[str]:
    """Tier-3 boots: what a FINISHED build wears.

    7.2 made tier 3 an upgrade of the matching tier 2 after 10:00, so the two do
    not compete for a slot; the tier 3 is simply the late-game state of it. A
    build scored at level 15 should therefore wear tier 3. Tier 2 still matters
    for the build ORDER, which greedy_order handles via upgradesFrom.
    """
    return [s for s, it in ITEMS.items() if it.get("bootsTier") == 3]


def best_boots(name: str, combo: list[str], runes: list[str], variant: str,
               role: str, fallback: str | None) -> str | None:
    """Keep the LLM's boots, upgraded to its tier-3 form.

    The engine used to search all 7 tier-3 boots and take the best score. That
    is the same mistake rune optimisation made: it optimises what it can SEE.
    Tenacity is not modeled at all (absent from _apply_stat and STAT_GOLD), so
    Mercury's Treads and Chainlaced Crushers can never be picked for the reason
    they exist -- when they won, they won on HP and MR, with their tenacity
    worth exactly zero. An LLM picks Mercury's "into heavy CC"; the engine
    structurally cannot. So the LLM decides (it is given boots' stats and full
    passives), and the engine only maps tier 2 -> its tier-3 upgrade.

    Revisit if tenacity/CC ever gets modeled.
    """
    if not fallback:
        return fallback
    it = ITEMS.get(fallback) or {}
    if it.get("bootsTier") == 2 and it.get("upgradesTo"):
        return it["upgradesTo"]        # the finished build wears the tier 3
    return fallback


def greedy_order(name: str, combo: list[str], boots: str | None,
                 runes: list[str], variant: str, role: str,
                 core: set[str] | None = None) -> list[str]:
    """Build order = early-game importance. CORE items always come first (in
    their own greedy order), then the rest — each step picks the item whose
    prefix scores highest at an early-mid level, so the rush is the item that
    actually carries the 10-minute game, not the late-game capstone.

    The TIER-3 BOOT UPGRADE is ordered as a real purchase. 7.2 made it a
    2000-2200g buy unlocked at 10:00, which is item money: it has to compete
    with the next item for the same gold, and where it wins is a power-spike
    question. Treating boots as one fixed thing (the old behaviour) both hid
    that choice and scored every early prefix as if you already wore tier 3.

    Returns (ordered_items, upgrade_after) where upgrade_after is how many items
    are bought before the upgrade, or None if there is no tier-3 for these boots.
    """
    t2 = _tier2_of(boots)
    upgradeable = bool(boots and t2 and t2 != boots)
    upgrade_after = BOOTS_UPGRADE_AFTER if upgradeable else None

    def _boots_at(n_items: int) -> str | None:
        """Which boots the build wears after n items: tier 2 until the upgrade
        lands, tier 3 after. Scoring every early prefix as if it already wore
        tier 3 overstated the first purchases."""
        if not upgradeable:
            return boots
        return boots if n_items >= upgrade_after else t2

    def _greedy(pool: list[str], ordered: list[str]) -> list[str]:
        out = list(ordered)
        remaining = list(pool)
        while remaining:
            best, best_s = remaining[0], float("-inf")
            # judge each candidate at the game stage where this purchase lands:
            # the Nth item is scored at the level/gold you'd realistically have,
            # so the rush is the item strongest AT THAT SPIKE, not at full build.
            n_purchases = len(out) + 1 + (1 if boots else 0)
            lvl = PREFIX_LEVELS[min(n_purchases - 1, len(PREFIX_LEVELS) - 1)]
            b = _boots_at(len(out) + 1)
            for cand in remaining:
                trial = out + [cand] + ([b] if b else [])
                s = score_items(name, trial, runes, variant, role,
                                fast=True, level=lvl)["score"]
                if s > best_s:
                    best, best_s = cand, s
            out.append(best)
            remaining.remove(best)
        return out

    core = core or set()
    core_items = [s for s in combo if s in core]
    rest = [s for s in combo if s not in core]
    ordered = _greedy(core_items, [])
    ordered = _greedy(rest, ordered)
    return ordered, upgrade_after


def _rune_modeled(rune_name: str) -> bool:
    """Only runes with numeric engine models can be differentiated by search."""
    return bool(RUNE_FX.get("keystones", {}).get(rune_name)
                or RUNE_FX.get("minors", {}).get(rune_name)
                or RUNE_ENGINE.get(rune_name))


def _page_names(bd: dict) -> tuple[str | None, list[str], str | None, str]:
    r = bd.get("runes") or {}
    ks = (r.get("keystone") or {}).get("name")
    minors = [m["name"] for m in r.get("treeMinors") or []]
    flex = (r.get("flexMinor") or {}).get("name")
    return ks, minors, flex, r.get("primaryTree", "")


def search_runes(name: str, items: list[str], variant: str, role: str,
                 bd: dict) -> dict | None:
    """Exhaustive slot-legal rune-page search over engine-modeled runes.

    Enumerates keystone x tree x (one minor per slot) x flex on the FINAL item
    set, using the fast score path. Only replaces the current page when the
    winner beats it — unmodeled runes all score identically, so the current
    (LLM-judged) page stays unless the math finds something strictly better."""
    cur_ks, cur_minors, cur_flex, _ = _page_names(bd)
    cur_page = ([cur_ks] if cur_ks else []) + cur_minors + ([cur_flex] if cur_flex else [])
    cur_score = score_items(name, items, cur_page, variant, role, fast=True)["score"]
    # Only replace a legal page when the winner is MEANINGFULLY better — sub-point
    # margins are model noise, and the LLM's page carries judgment the engine
    # can't score (unmodeled utility runes). Illegal pages are always replaced.
    if sorted(SLOT_OF.get(n, 0) for n in cur_minors) != [1, 2, 3]:
        cur_score = float("-inf")
    else:
        cur_score += 1.5  # epsilon: the incumbent wins ties

    keystones = sorted({r["name"] for r in RUNES_ALL if r["type"] == "Keystone"
                        and (_rune_modeled(r["name"]) or r["name"] == cur_ks)})
    flex_pool = sorted({r["name"] for r in RUNES_ALL if r["type"] == "Minor"
                        and (_rune_modeled(r["name"]) or r["name"] == cur_flex)})

    best = (cur_score, None)
    pages = 0
    for tree, slots in RUNE_SLOTS.items():
        pools = []
        for s in ("1", "2", "3"):
            names = slots.get(s, [])
            modeled = [n for n in names if _rune_modeled(n)]
            keep_cur = [n for n in names if n in cur_minors]
            pool = sorted(set(modeled + keep_cur)) or names[:1]
            pools.append(pool)
        for a in pools[0]:
            for b2 in pools[1]:
                for c in pools[2]:
                    trio = (a, b2, c)
                    for ks in keystones:
                        for fx in flex_pool:
                            if fx in trio:
                                continue
                            pages += 1
                            page = [ks, a, b2, c, fx]
                            s = score_items(name, items, page, variant, role, fast=True)["score"]
                            if s > best[0]:
                                best = (s, {"keystone": ks, "tree": tree,
                                            "minors": list(trio), "flex": fx})
    if not best[1]:
        return {"pages": pages, "kept": True, "score": cur_score}
    return {"pages": pages, "kept": False, "score": best[0], "prev": cur_score,
            **best[1]}


def _rune_entry(rune_name: str, reason: str = "") -> dict:
    r = RUNE_BY_NAME[rune_name]
    return {"name": r["name"], "slug": r["slug"], "tree": r.get("tree", ""),
            "icon": r["icon"], "reason": reason}


def apply_rune_page(bd: dict, res: dict) -> None:
    old = bd.get("runes") or {}
    old_reason = {}
    for m in old.get("treeMinors") or []:
        old_reason[m["name"]] = m.get("reason", "")
    if old.get("flexMinor"):
        old_reason[old["flexMinor"]["name"]] = old["flexMinor"].get("reason", "")
    if old.get("keystone"):
        old_reason[old["keystone"]["name"]] = old["keystone"].get("reason", "")
    ksr = _rune_entry(res["keystone"], old_reason.get(res["keystone"], ""))
    bd["runes"] = {
        "keystone": {"name": ksr["name"], "slug": ksr["slug"], "icon": ksr["icon"],
                     "reason": ksr["reason"]},
        "primaryTree": res["tree"],
        "treeMinors": [_rune_entry(n, old_reason.get(n, "")) for n in res["minors"]],
        "flexMinor": _rune_entry(res["flex"], old_reason.get(res["flex"], "")),
    }


def search_variant(name: str, rec: dict, variant: str, bd: dict, llm: LLM) -> dict | None:
    role = rec.get("role", "")
    champ = CHAMPS.get(name)
    if not champ:
        return None
    current_items, runes = _build_lists(bd)
    boots = bd.get("boots", {}).get("slug") if bd.get("boots") else None
    current_core = [s for s in current_items if s != boots]

    pool = propose_pool(llm, champ, rec.get("class", "?"), role, variant, current_core)
    if len(pool) < 6:
        return None

    bounds = IDENTITY_BOUNDS.get(variant, (0, 2, 0, 3))
    if variant == "tanky" and rec.get("class") == "Tank":
        # Only true tanks may go full tank -- and only a tank SUPPORT may go all
        # the way. A jungle/baron tank must keep a damage slot.
        bounds = TANKY_FULL_TANK if role == "Support" else TANKY_SOLO_TANK
    elif variant == "standard" and rec.get("class") in STANDARD_BY_CLASS:
        bounds = STANDARD_BY_CLASS[rec["class"]]
    t_lo, t_hi, d_lo, d_hi = bounds
    if sum(1 for s in pool if is_tank(s)) < t_lo:
        t_lo = 0  # pool can't supply the tank minimum
    if sum(1 for s in pool if is_defensive(s)) < d_lo:
        d_lo = 0  # pool can't supply the defensive minimum (e.g. mage pools)
    # MAXIMUMS need the same escape hatch, and only minimums had one. A cap of
    # d_hi=4 means "at least one of the five must be non-defensive" -- so if the
    # shortlist is ALL defensive (which is what an LLM hands you for "tanky"),
    # every combo breaks the cap and the search returns nothing at all. That is
    # exactly what killed Malphite/tanky: the variant was silently skipped and
    # kept its old build. A cap we cannot satisfy must yield, not delete the
    # build.
    if sum(1 for s in pool if not is_defensive(s)) < 5 - d_hi:
        d_hi = 5
    if sum(1 for s in pool if not is_tank(s)) < 5 - t_hi:
        t_hi = 5
    crit_lo = CRIT_MIN.get(variant, 0)
    if sum(1 for s in pool if is_crit(s)) < crit_lo:
        crit_lo = 0  # pool can't supply the crit minimum; don't return nothing
    scored: list[tuple[float, tuple[str, ...]]] = []
    for combo in combinations(pool, 5):
        if not legal(combo):
            continue
        n_tank = sum(1 for s in combo if is_tank(s))
        n_def = sum(1 for s in combo if is_defensive(s))
        if not (t_lo <= n_tank <= t_hi and d_lo <= n_def <= d_hi):
            continue
        if sum(1 for s in combo if is_crit(s)) < crit_lo:
            continue
        items = list(combo) + ([boots] if boots else [])
        # fast=True: skips the iterative TTK solve, which is 48 extra rotation
        # calls that fight_score never reads. Identical score, 2.2x faster, and
        # this loop runs ~2000 times per variant.
        s = score_items(name, items, runes, variant, role, fast=True)["score"]
        scored.append((s, combo))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)

    # POLISH over the FULL pool, not just the LLM's 14.
    #
    # The shortlist is the hard ceiling of this search: the engine can only pick
    # 5 of 14, so an item the LLM omits is unbuildable however well it scores.
    # That ceiling is real and it is expensive -- Divine Sunderer scored +12.7
    # over Trinity Force on Hecarim/standard and was simply not shortlisted,
    # while the SAME model shortlisted it for Xin Zhao (same class, same role).
    # So the omission is inconsistency, not judgement.
    #
    # Bumping POOL_SIZE is the weak answer: 14 -> 20 costs 7.7x the combos
    # (2002 -> 15504) and still only hopes the model lists the item. A single
    # swap pass over all ~98 candidates is ~500 score calls, runs in seconds,
    # and GUARANTEES no single-item omission survives.
    #
    # It is a hill-climb, so it cannot find a PAIR of items that only work
    # together. The combinatorial search over the 14 still covers that, which is
    # why both stages exist rather than one replacing the other.
    best_combo_l = list(scored[0][1])
    best_s = scored[0][0]
    # The polish searches the FULL pool, so it must honour the same rules the
    # shortlist filter does -- otherwise it quietly re-introduces exactly what
    # the filter excluded (an AD carry item on an AP kit).
    _cls = rec.get("class", "")
    all_cands = [s for s in ITEMS
                 if ITEMS[s]["category"] not in ("Boots", "Enchantment")
                 and s not in SITUATIONAL_ONLY
                 and item_allowed(s, name, _cls, role)]
    improved = True
    swaps: list[str] = []
    while improved:
        improved = False
        for i in range(len(best_combo_l)):
            for cand in all_cands:
                if cand in best_combo_l:
                    continue
                trial = best_combo_l[:i] + [cand] + best_combo_l[i + 1:]
                if not legal(tuple(trial)):
                    continue
                n_tank = sum(1 for s in trial if is_tank(s))
                n_def = sum(1 for s in trial if is_defensive(s))
                if not (t_lo <= n_tank <= t_hi and d_lo <= n_def <= d_hi):
                    continue
                if sum(1 for s in trial if is_crit(s)) < crit_lo:
                    continue      # a swap must not quietly break the identity
                s = score_items(name, trial + ([boots] if boots else []),
                                runes, variant, role, fast=True)["score"]
                if s > best_s + 0.05:      # epsilon: ignore model noise
                    swaps.append(f"{best_combo_l[i]}->{cand} (+{s - best_s:.1f})")
                    best_combo_l, best_s = trial, s
                    improved = True
        # re-loop: a swap can unlock another
    if swaps:
        scored = [(best_s, tuple(best_combo_l))] + scored
        scored.sort(key=lambda x: x[0], reverse=True)

    top = scored[:TOP_K]
    freq: dict[str, int] = {}
    for _s, combo in top:
        for slug in combo:
            freq[slug] = freq.get(slug, 0) + 1
    core = {s for s, n in sorted(freq.items(), key=lambda kv: -kv[1])[:3]
            if n / len(top) >= CORE_FREQ}

    best_score, best_combo = scored[0]
    # Boots are chosen, not inherited. Done after the combo search rather than
    # inside it: 14 boots x every 5-item combo is a 14x blow-up for a slot that
    # barely interacts with the rest of the build, so search the items against
    # the incumbent boots, then fit the best boots to the winner.
    boots = best_boots(name, list(best_combo), runes, variant, role, boots)
    ordered, upgrade_after = greedy_order(name, list(best_combo), boots, runes,
                                          variant, role, core)
    baseline = score_items(name, current_items, runes, variant, role)["score"]
    return {"ordered": ordered, "core": core, "score": best_score,
            "baseline": baseline, "combos": len(scored), "pool": len(pool),
            "poolSlugs": pool, "boots": boots, "bootsTier2": _tier2_of(boots),
            "bootsUpgradeAfter": upgrade_after, "swaps": swaps}


def _tier2_of(boots: str | None) -> str | None:
    """The tier-2 a tier-3 boot upgrades from: what you actually buy before
    10:00. The final build wears the tier 3; the early build wears this."""
    if not boots:
        return None
    for s, it in ITEMS.items():
        if it.get("upgradesTo") == boots:
            return s
    return boots if (ITEMS.get(boots) or {}).get("bootsTier") == 2 else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    # OFF by default, and coverage was never the real problem. Even at 49/53
    # modeled runes the search optimises a NUMBER, not a kit: it has no idea
    # Guardian is a support keystone, so it handed a solo jungler a support page
    # and took all five slots from one tree. Damage/EHP is simply not what makes
    # a rune page good -- mobility, cooldown timing and lane pattern are, and
    # none of those are simulated. The LLM's page carries that judgement, so it
    # stays unless it is slot-ILLEGAL, which the engine always repairs.
    ap.add_argument("--optimize-runes", action="store_true",
                    help="let the engine REPLACE legal rune pages it out-scores. "
                         "Off by default: the score cannot see kit fit (it picked "
                         "Guardian, a support keystone, on junglers). "
                         "Slot-legality fixes always run.")
    args = ap.parse_args()
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is not set")
    llm = LLM("deepseek", "deepseek-v4-flash")

    builds = json.loads(BUILDS.read_text(encoding="utf-8"))
    only = {n.strip() for n in args.only.split(",") if n.strip()}
    names = [n for n in builds if (not only or n in only) and n in FORMULAS]
    print(f"{len(names)} champions to search")

    for name in names:
        rec = builds[name]
        new_reasons_needed: dict[str, list[str]] = {}
        for variant, bd in (rec.get("builds") or {}).items():
            try:
                res = search_variant(name, rec, variant, bd, llm)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {name}/{variant}: {e}")
                continue
            if not res:
                print(f"  ! {name}/{variant}: no legal combos in pool — skipped")
                continue
            old_by_slug = {i["slug"]: i for i in bd["coreBuild"]}
            bd["coreBuild"] = [{
                "slug": s, "name": ITEMS[s]["name"], "cost": ITEMS[s]["cost"],
                "icon": ITEMS[s]["icon"],
                "reason": old_by_slug.get(s, {}).get("reason", ""),
                **({"core": True} if s in res["core"] else {}),
            } for s in res["ordered"]]

            # Boots are a searched decision now, so write them back: the tier-3
            # the finished build wears, the tier-2 you actually buy early, and
            # WHERE in the order the upgrade lands (it costs item money, so the
            # optimizer places it against the next item's power spike).
            def _tile(slug: str | None) -> dict | None:
                if not slug or slug not in ITEMS:
                    return None
                it = ITEMS[slug]
                return {"slug": slug, "name": it["name"], "cost": it["cost"],
                        "icon": it["icon"]}

            t3, t2 = res.get("boots"), res.get("bootsTier2")
            if t3:
                prev_reason = (bd.get("boots") or {}).get("reason", "")
                bd["boots"] = {**_tile(t3), "reason": prev_reason}
                if t2 and t2 != t3:
                    bd["bootsEarly"] = _tile(t2)
                    bd["bootsUpgradeAfter"] = res.get("bootsUpgradeAfter")
                else:
                    bd.pop("bootsEarly", None)
                    bd.pop("bootsUpgradeAfter", None)

            bd["searched"] = {"combos": res["combos"], "poolSize": res["pool"],
                              "pool": res["poolSlugs"],
                              "engineScore": res["score"], "llmBaseline": res["baseline"]}

            # rune-page search on the final items (slot-legal by construction)
            items, _ = _build_lists(bd)
            # Only SEARCH if the result can be used. The search enumerates ~35k
            # pages -- 3.6 min per variant, ~95% of this script's entire runtime
            # -- and with optimisation off every page of it was computed and then
            # discarded by `protected` below. It exists to repair slot-ILLEGAL
            # pages, and legality is a dict lookup, so check that first.
            _ks, _minors, _flex, _tree = _page_names(bd)
            page_illegal = sorted(SLOT_OF.get(n, 0) for n in _minors) != [1, 2, 3]
            rres = None
            if page_illegal or args.optimize_runes:
                try:
                    rres = search_runes(name, items, variant, rec.get("role", ""), bd)
                except Exception as e:  # noqa: BLE001
                    print(f"    ! rune search failed for {variant}: {e}")
                    rres = None
            # Enchanter/utility pages stay protected even with optimisation on.
            # support_value now prices rune ally effects (Font of Life's ally
            # heal, Guardian's ally shield), but those are the ONLY two ally
            # runes modeled, so the search still can't see most of what makes an
            # enchanter page good. Narrow carve-out, revisit when more land.
            protected = (rec.get("class") == "Enchanter" or variant == "utility"
                         or not args.optimize_runes)
            was_illegal = rres and rres.get("prev") == float("-inf")
            if rres and not rres.get("kept") and (not protected or was_illegal):
                apply_rune_page(bd, rres)
                prev_s = "illegal page" if was_illegal else f"{rres.get('prev'):g}"
                print(f"    runes {variant}: {rres['pages']} pages -> "
                      f"{rres['keystone']} | {rres['tree']} (was {prev_s}, now {rres['score']:g})")
                bd["searched"]["runes"] = {"pages": rres["pages"], "score": rres["score"]}
            items, runes = _build_lists(bd)
            bd["engine"] = score_items(name, items, runes, variant, rec.get("role", ""))
            bd["engine"]["curve"] = build_curve(name, items, runes, variant, rec.get("role", ""))
            new_reasons_needed[variant] = [s for s in res["ordered"]
                                           if not old_by_slug.get(s, {}).get("reason")]
            delta = res["score"] - res["baseline"]
            print(f"  {name}/{variant}: {res['combos']} combos from pool {res['pool']} "
                  f"-> score {res['score']:g} (LLM build was {res['baseline']:g}, "
                  f"{'+' if delta >= 0 else ''}{delta:.1f})")
            # The shortlist is the biggest lever in the whole search: the engine
            # can only ever pick 5 of THESE, so an item the LLM leaves out is
            # unbuildable no matter how well it scores. Print it to make that
            # filter reviewable instead of invisible.
            chosen = {s for s in res["ordered"]}
            print(f"      pool: " + ", ".join(
                (f"*{s}" if s in chosen else s) for s in res["poolSlugs"]))
            print(f"      picked: {' > '.join(res['ordered'])}"
                  f"  | boots {res.get('bootsTier2')} -> {res.get('boots')}"
                  f" after {res.get('bootsUpgradeAfter')} items")
            if res.get("swaps"):
                print(f"      polish (items the shortlist missed): "
                      f"{', '.join(res['swaps'])}")

        # one reasons pass per champion for items that changed
        want = {v: slugs for v, slugs in new_reasons_needed.items() if slugs}
        if want:
            listing = json.dumps({v: [f"{s} ({ITEMS[s]['name']})" for s in slugs]
                                  for v, slugs in want.items()})
            try:
                reasons = _extract_json(llm.generate(
                    [f"CHAMPION: {name}\nItems per variant needing reasons: {listing}\n"
                     f"Return the JSON now."], 0.2, REASON_SYSTEM))
                for v, slugs in want.items():
                    per = reasons.get(v) or {}
                    by_slug = {i["slug"]: i for i in rec["builds"][v]["coreBuild"]}
                    for s in slugs:
                        txt = per.get(s) or per.get(ITEMS[s]["name"]) or ""
                        if s in by_slug and txt:
                            by_slug[s]["reason"] = str(txt)[:120]
            except Exception as e:  # noqa: BLE001
                print(f"    reasons pass failed ({e}) — keeping blank reasons")

        payload = json.dumps(builds, ensure_ascii=False, indent=2)
        BUILDS.write_text(payload, encoding="utf-8")
        WEB_OUT.write_text(payload, encoding="utf-8")

    print("\nsearch complete")


if __name__ == "__main__":
    main()
