"""Structured item metadata, and a deliberately timid candidate filter.

Two jobs, and it matters that they stay separate:

  1. Describe each item in machine-readable terms -- what it needs from a kit to
     be worth its gold, when in the game it pays off, which groups it belongs
     to. Derived from the item text, never hand-typed, so it stays true across
     a patch. This does NOT replace the item description sent to the model: the
     current-patch text remains the factual source, and this is scaffolding for
     filtering and validation.

  2. Remove candidates that are *impossible*, not merely unusual. The bar is
     high on purpose. An item that a normal build would never take but that has
     a credible kit, timing or matchup argument must survive to the model,
     because filtering it here removes it from consideration silently and no
     amount of good reasoning downstream can get it back. Every exclusion is
     recorded with a reason so the decision is auditable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"


def _load(name: str, default=None):
    path = DATA / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


ITEMS: dict[str, dict] = {i["slug"]: i for i in _load("items.json", [])}
RULES: dict = _load("item_rules.json", {}) or {}

HARD_EXCLUSIVE: dict[str, list[str]] = {
    name: group["slugs"]
    for name, group in (RULES.get("hardExclusive") or {}).items()
    if not name.startswith("_") and isinstance(group, dict)
}
REDUNDANCY: dict[str, dict] = {
    name: group
    for name, group in (RULES.get("redundancyGroups") or {}).items()
    if not name.startswith("_") and isinstance(group, dict)
}
SITUATIONAL_ONLY: set[str] = set((RULES.get("situationalOnly") or {}).get("slugs", []))
LATE_STRATEGIC: dict[str, dict] = {
    slug: cfg for slug, cfg in (RULES.get("lateGameStrategic") or {}).items()
    if not slug.startswith("_") and isinstance(cfg, dict)
}


def completed_items() -> dict[str, dict]:
    """The pool the model may build from: completed, non-boots items."""
    return {
        slug: item for slug, item in ITEMS.items()
        if item.get("category") != "Boots"
        and not (set(item.get("categories") or []) & {"Basic", "MidTier"})
    }


# Wild Rift allows at most ONE active item in a build. An active item is one with
# a named "(Active)" / "Active:" clause in its passive text -- Zhonya's Stasis,
# Gargoyle's Stoneplate, Locket, Shurelya's and the rest. Detected from the data
# rather than listed by hand, so it stays correct across a patch.
_ACTIVE_CLAUSE = re.compile(r"\(active\)|\bactive\s*:", re.I)
ACTIVE_ITEMS: set[str] = {
    slug for slug, item in ITEMS.items()
    if item.get("category") != "Boots"
    and _ACTIVE_CLAUSE.search(" ".join(item.get("passives") or []))
}


def active_items_in(slugs: list[str]) -> list[str]:
    """Which of these slugs carry an activatable effect."""
    return [s for s in slugs if s in ACTIVE_ITEMS]


# --------------------------------------------------------------------------
# passive tags: what an item's text says it needs, or gives
# --------------------------------------------------------------------------

# Each tag is a claim about the item that we can check against a champion's
# combat profile. Patterns stay narrow: a tag that over-matches would filter out
# a legitimate item, which is the one failure mode this module must not have.
_PASSIVE_TAGS: dict[str, re.Pattern] = {
    "spellblade": re.compile(r"\bspellblade\b", re.I),
    "on-hit": re.compile(r"on[- ]hits?\b", re.I),
    "attack-speed-scaling": re.compile(r"attack speed", re.I),
    "crit-scaling": re.compile(r"critical strike|crit\b", re.I),
    "grievous-wounds": re.compile(r"grievous wounds|healing.{0,20}reduc", re.I),
    "anti-shield": re.compile(r"shield.{0,25}(?:reduc|less|break)|reduc.{0,20}shield", re.I),
    "movement-speed": re.compile(r"movement speed", re.I),
    "healing": re.compile(r"\bheal|omnivamp|life ?steal|physical vamp|spell vamp", re.I),
    "shielding": re.compile(r"grants? a shield|shield that absorbs|absorbs up to", re.I),
    "revive": re.compile(r"resurrect|revive|stasis", re.I),
    "mana-dependent": re.compile(r"\bmana\b", re.I),
    "ability-haste": re.compile(r"ability haste", re.I),
    "armor-penetration": re.compile(r"armor pen|armor.{0,15}reduc|physical pen|last whisper", re.I),
    "magic-penetration": re.compile(r"magic pen", re.I),
    "max-health-damage": re.compile(r"max(?:imum)? health", re.I),
}

# Range restriction, parsed rather than pattern-matched, because the one item in
# the pool that has one states it backwards. Runaan's Hurricane reads "This item
# cannot only be used by melee champions" -- a mangled scrape of a restriction
# that, either way it is untangled, means melee champions cannot build it. A
# naive "only ... melee" match tags it melee-only and then hides it from every
# marksman, which is precisely backwards.
_RESTRICTION = re.compile(r"\bused\s+by\s+(?P<who>melee|ranged)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:cannot|can\s*not|may\s*not|never|not)\b", re.IGNORECASE)

# The project already answers "is this champion ranged" in two places
# (web/fight_engine.py and web-next/src/lib/build-scaling.ts) with the same set.
# No champion record carries an attack type, so class is the available signal;
# a third convention here would just be a third thing to keep in sync.
RANGED_CLASSES = {"Marksman", "Mage", "Enchanter"}

# Mirrored from web/advisor/supportitem.py, which owns the rule. Named here to
# keep this module import-free at the top level.
_SUPPORT_ITEMS = frozenset({"bulwark-of-the-mountain", "black-mist-scythe"})


def _range_restriction(blob: str) -> str:
    """'melee-only', 'ranged-only', or '' when the item is open to everyone.

    The negation has to be looked for separately rather than as an optional
    group in one pattern: with the negation optional, the leftmost match wins
    and the engine happily matches it as empty at the start of the sentence,
    reading "cannot only be used by melee" as a melee restriction.
    """
    match = _RESTRICTION.search(blob)
    if not match:
        return ""
    who = match.group("who").lower()
    # Only the run-up to the phrase counts -- a "not" later in the passive is
    # about something else entirely.
    preceding = blob[max(0, match.start() - 60):match.start()]
    negated = bool(_NEGATION.search(preceding))
    if negated:
        return "ranged-only" if who == "melee" else "melee-only"
    return "melee-only" if who == "melee" else "ranged-only"

# Cost is a blunt but honest proxy for when an item lands. Wild Rift games run
# 15-20 minutes, so a 3000g+ item is realistically a third purchase or later.
_TEMPO_BY_COST = ((2400, "early"), (3050, "early-mid"), (3400, "mid-late"))


def _tempo(cost: int) -> str:
    for ceiling, label in _TEMPO_BY_COST:
        if cost < ceiling:
            return label
    return "late"


def _stat_keys(item: dict) -> list[str]:
    return sorted((item.get("stats") or {}).keys())


def metadata(slug: str) -> dict:
    """Structured description of one item. Derived, never asserted."""
    item = ITEMS.get(slug) or {}
    blob = " ".join(item.get("passives") or [])
    stats = item.get("stats") or {}
    stat_keys = set(stats)
    tags = sorted(
        tag for tag, pattern in _PASSIVE_TAGS.items()
        if pattern.search(blob)
        # A stat key counts as evidence too: an item with a `magicPen` stat has
        # magic penetration whether or not its prose says so.
        or tag.replace("-", "") in {k.lower() for k in stat_keys}
    )
    if "mana" in stat_keys and "mana-dependent" not in tags:
        tags.append("mana-dependent")
    restriction = _range_restriction(blob)
    if restriction:
        tags.append(restriction)
        tags.sort()

    cost = int(item.get("cost") or 0)
    # Activation delay: a stacking or transform item (tear line, stack-to-cap
    # passives) is not "immediate" even when cheap; everything else pays off on
    # completion. Derived from the passive text, low-confidence by nature.
    _delayed = re.compile(r"\bstack|per (kill|takedown|minion)|transform|charges?\b|"
                          r"upon reaching|permanently", re.I)
    activation_delay = "delayed" if _delayed.search(blob) else "immediate"
    resource_dependency = "mana" if ("mana" in stat_keys or "mana-dependent" in tags) else "none"

    # `active` is a tag like any other so the pool carries the signal. Without
    # it the model's only exposure to actives was the hard-legality rule that
    # caps them at one and named eleven of them, which reads as a list of items
    # to avoid -- the safest way never to break that rule is to buy none, and
    # that is roughly what the builds showed.
    if slug in ACTIVE_ITEMS:
        tags = sorted({*tags, "active"})

    return {
        "slug": slug,
        "name": item.get("name", slug),
        "category": item.get("category", ""),
        "cost": cost,
        "completionCost": cost,
        "primaryStats": _stat_keys(item),
        "passiveTags": tags,
        "tempoProfile": _tempo(cost),
        # Cost is a proxy for tempo, not proof: an expensive item can still be an
        # early spike, and a cheap one can be too conditional to rush. The label
        # is a hint, not a fact -- callers should not treat it as high-confidence.
        "tempoConfidence": "low",
        "activationDelay": activation_delay,
        "resourceDependency": resource_dependency,
        "requiresMana": resource_dependency == "mana",
        "meleeAllowed": "ranged-only" not in tags,
        "rangedAllowed": "melee-only" not in tags,
        "situationalTags": ["reactive"] if slug in SITUATIONAL_ONLY else [],
        "hasActive": slug in ACTIVE_ITEMS,
        "exclusiveGroups": ([n for n, slugs in HARD_EXCLUSIVE.items() if slug in slugs]
                            + (["active-item"] if slug in ACTIVE_ITEMS else [])),
        "redundancyGroups": [n for n, g in REDUNDANCY.items() if slug in g.get("slugs", [])],
        "lateGameStrategic": slug in LATE_STRATEGIC,
    }


def all_metadata() -> dict[str, dict]:
    return {slug: metadata(slug) for slug in completed_items()}


# --------------------------------------------------------------------------
# candidate filtering: only the impossible, never the merely unusual
# --------------------------------------------------------------------------

# Stat keys that carry no value at all for a champion with no mana bar. Note
# `manaRegen` is included but `abilityHaste` is not: haste is universally useful.
_MANA_STATS = {"mana", "manaRegen"}

# Ceiling on the mandatory audit. The audit obliges the model to produce a score
# and a reason for every entry, so an unbounded list quietly becomes the whole
# response. Fifteen is roughly the size of the competitive candidate set, which
# is the most it should ever cost.
_MAX_AUDIT_ITEMS = 15


def _is_manaless(champion_record: dict) -> bool:
    """A champion with no mana pool in the verified base stats."""
    base = (champion_record.get("baseStats") or {}).get("mana") or {}
    return not float(base.get("base") or 0)


def filter_candidates(
    champion_record: dict,
    combat_profile: dict,
    scaling_profile: dict,
    damage_path: str = "standard",
    enemies_known: bool = False,
    role: str = "",
) -> tuple[list[str], list[dict]]:
    """Split the pool into what the model sees and what it does not.

    Returns (kept_slugs, removed) where each removed entry carries the reason.
    The caller logs `removed` so a filtering mistake is visible rather than
    silent -- that log is the only thing standing between a conservative filter
    and a filter that quietly narrows every build to the same five items.
    """
    kept: list[str] = []
    removed: list[dict] = []
    manaless = _is_manaless(champion_record)
    # Ask profiles rather than re-deriving from the class here. This used to be
    # its own `class in RANGED_CLASSES` check, which ignored the curated
    # rangeProfile overrides entirely -- so every melee champion classed as a
    # Mage (Akali, Katarina, Diana, Lillia...) counted as ranged for item
    # filtering and was offered Runaan's Hurricane, which they cannot use.
    # Pure ranged only. A hybrid (Gnar, Jayce) has a melee mode, and an item
    # that switches off when they transform is not an item they can build.
    from web.advisor import profiles  # local: keeps module import order free
    ranged = profiles.is_pure_ranged(champion_record.get("name", ""))

    def drop(slug: str, reason: str) -> None:
        removed.append({"item": slug, "reason": reason})

    for slug, item in completed_items().items():
        meta = metadata(slug)
        stats = set(item.get("stats") or {})
        tags = set(meta["passiveTags"])

        # 1. Mana on a manaless kit. Only when mana is ALL the item does -- an
        #    item with mana plus AD plus a passive still has a case.
        if manaless and stats and stats <= _MANA_STATS:
            drop(slug, "champion has no mana pool and this item's stats are mana only")
            continue

        # 2. The free support items, which are income for the support and dead
        #    weight for anyone else -- their value is Soulcast's gold, and only
        #    the support collects it. Offering them outside the role invited a
        #    solo laner to spend a slot on 10 ability haste.
        if slug in _SUPPORT_ITEMS and (role or "").strip().lower() != "support":
            drop(slug, "free support item and this is not a support build")
            continue

        # 3. Range restriction printed on the item itself.
        if ranged and not meta["rangedAllowed"]:
            drop(slug, "item is melee-only and this champion is ranged")
            continue
        if not ranged and not meta["meleeAllowed"]:
            drop(slug, "item is ranged-only and this champion is melee")
            continue

        # 3. Reactive items with nothing to react to. They come back the moment
        #    an enemy team is supplied, and they are still offered as swaps.
        if not enemies_known and slug in SITUATIONAL_ONLY:
            drop(slug, "reactive item and no enemy team was supplied; offered as a "
                       "situational swap instead of a main-build candidate")
            continue

        # 4. An explicitly requested damage path. This is a user instruction, so
        #    it is the one place we filter on preference rather than possibility.
        if damage_path == "ad" and stats and stats <= {"ap", "abilityHaste", "mana", "manaRegen"}:
            drop(slug, "AD damage path was requested and this item offers no AD")
            continue
        if damage_path == "ap" and stats and stats <= {"ad", "attackSpeed", "crit"}:
            drop(slug, "AP damage path was requested and this item offers no AP")
            continue

        kept.append(slug)

    return sorted(kept), removed


def item_pipeline_trace(
    slugs: list[str],
    champion_record: dict,
    combat_profile: dict,
    scaling_profile: dict,
    *,
    damage_path: str = "standard",
    enemies_known: bool = False,
    damage_identity: str = "",
) -> list[dict]:
    """Development trace: where each named item stands in the generation pipeline.

    Answers, for items like eclipse / sundered-sky / dusk-and-dawn, whether they
    are in the source pool, survived the pre-filter, would appear in the prompt,
    and whether they are pulled into the mandatory audit. It does NOT run the
    model, so it cannot report the final score -- but it distinguishes "never
    offered" from "offered and legitimately not selected". Debug/eval only.
    """
    pool = completed_items()
    kept, removed = filter_candidates(
        champion_record, combat_profile, scaling_profile,
        damage_path=damage_path, enemies_known=enemies_known)
    withheld = {r["item"]: r["reason"] for r in removed}
    audit = set(mandatory_audit(combat_profile, scaling_profile, damage_identity))
    out = []
    for slug in slugs:
        out.append({
            "item": slug,
            "sourcePoolPresent": slug in ITEMS,
            "completedNonBoots": slug in pool,
            "passedPrefilter": slug in kept,
            "withheldReason": withheld.get(slug),
            "includedInPrompt": slug in kept,          # the prompt pool IS `kept`
            "inMandatoryAudit": slug in audit,
            "passiveTags": metadata(slug)["passiveTags"] if slug in ITEMS else [],
        })
    return out


def mandatory_audit(combat_profile: dict, scaling_profile: dict,
                    damage_identity: str = "") -> list[str]:
    """Items whose text matches this kit closely enough to demand a verdict.

    This replaces the old `onHit` tag audit, which fired for 85 of 141 champions
    and forced every on-hit item into the comparison set for kits that apply
    on-hit once. The audit list is now built from the derived profile, so a
    champion who weaves one empowered attack is audited on spellblade items,
    and only a champion who genuinely relies on repeated application is audited
    on attack-speed and on-hit stacking.
    """
    wanted: set[str] = set()

    def add_by_tag(tag: str) -> None:
        for slug in completed_items():
            if tag in metadata(slug)["passiveTags"]:
                wanted.add(slug)

    # Only tags that genuinely single out a small set of items belong here. A
    # tag matching a third of the pool -- "movement speed", "healing" -- is a
    # stat, not a kit mechanic, and auditing on it swamps the list: an early
    # version keyed on those two produced a 60-item audit for Hecarim, which is
    # worse than the 7-item version it replaced. Those signals reach the model
    # through the scaling notes instead, where they cost nothing.
    if combat_profile.get("spellbladeProcReliability") == "high":
        add_by_tag("spellblade")
    if combat_profile.get("repeatedOnHitReliance") == "high":
        add_by_tag("on-hit")
    if combat_profile.get("critValue") == "high":
        add_by_tag("crit-scaling")

    # Actives, every time. They were being skipped almost entirely: on a Lux
    # studio build the model scored 16 of 95 candidates and only ONE active
    # reached the shortlist -- Zhonya's, at 82, with a sound reason -- and it
    # still did not make the five. A high score does not put an item in a build;
    # a demand for a verdict does, which is what this list is for.
    #
    # Filtered by damage identity from the item's own stat line, so a physical
    # assassin is not asked to rule on Redemption. Stat-neutral actives
    # (Gargoyle, Locket, Mikael's) are relevant to anyone and stay in.
    for slug in ACTIVE_ITEMS:
        if slug not in completed_items():
            continue
        stats = set(ITEMS.get(slug, {}).get("stats") or {})
        offensive = stats & {"ap", "ad"}
        if offensive and not damage_identity:
            # Identity unknown: keep only the stat-neutral actives. Including
            # everything here handed Annie a verdict to write on Galeforce.
            continue
        if "ap" in stats and damage_identity == "physical":
            continue
        if "ad" in stats and damage_identity == "magic":
            continue
        wanted.add(slug)

    # The audit is a demand for a verdict on every entry, so its cost is real:
    # each item spends output tokens the competitive comparison could use. If a
    # trigger somehow still matches broadly, keep the cheapest items -- the ones
    # most likely to be an early-purchase mistake worth ruling out explicitly.
    ordered = sorted(wanted, key=lambda s: (ITEMS.get(s, {}).get("cost", 0), s))
    return sorted(ordered[:_MAX_AUDIT_ITEMS])
