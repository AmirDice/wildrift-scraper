"""Champion combat and scaling profiles, derived rather than tagged.

Why this module exists
----------------------
The champion records carry two coarse fields, `mechanics` and `scalesWith`, both
produced by substring matching in scripts/scrape_champions.py. Across the 141
champion roster they are close to constant and therefore close to useless as
discriminators:

    onHit  85/141      cc 134/141      heal 109/141      dash 96/141
    ap    117/141      ad  80/141      attackSpeed 64/141

`onHit` fires on the literal string "next attack", so Hecarim -- whose E reads
"if his next attack is within 5 seconds" -- is tagged an on-hit champion and the
mandatory item audit then forces Guinsoo's, Nashor's, Runaan's and Terminus into
his comparison set. `ap` fires on "ability power" appearing anywhere, so 83% of
the roster "scales with AP".

So we derive richer profiles here instead of trying to patch the tags. Two
sources, in priority order:

  1. data/ability_formulas.json -- properly parsed ratios with hit counts,
     per-cast vs per-auto, and stat-conversion steroids. Covers 31 champions.
  2. The raw ability text, via regex. Covers 140 of 141.

Cooldowns come from the champion record (all 141 have them) and are what make
the weighting honest: a 100% AP ratio on a 85-second ultimate is not the same
scaling claim as a 110% AD ratio on a 4-second basic ability, and a share that
ignores cooldown says they are.

What this module will NOT do
----------------------------
It does not invent numbers. Where a signal cannot be derived, the field is
omitted rather than filled with a plausible-looking default -- an absent
`effectiveScalingWeights` is information, a fabricated one is noise. Curated
overrides live in data/combat_profiles.json for the cases where the rules below
are genuinely wrong, and they are the only place a human number enters.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "data"


def _load(name: str, default=None):
    path = DATA / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


_CHAMPS_RAW = _load("champions_wr.json", [])
CHAMPIONS: dict[str, dict] = {
    c["name"]: c
    for c in (_CHAMPS_RAW.values() if isinstance(_CHAMPS_RAW, dict) else _CHAMPS_RAW)
}
FORMULAS: dict[str, dict] = _load("ability_formulas.json", {}) or {}
ARCHETYPES: dict[str, dict] = _load("champion_archetypes.json", {}) or {}
OVERRIDES: dict[str, dict] = (_load("combat_profiles.json", {}) or {}).get("champions", {})

# Class and role are not in the champion scrape -- they live in the builds file
# and the site roster. Without them a Marksman reads as an unclassified kit and
# the attack-pattern rules below fall through to the wrong branch, so fold them
# in exactly as build_advisor.py does.
for _source in ("../web-next/src/data/builds.json", "champion_builds.json",
                "../web-next/src/data/roster.json"):
    _records = _load(_source, None)
    if not _records:
        continue
    _iterable = _records.values() if isinstance(_records, dict) else _records
    for _rec in _iterable:
        _name = _rec.get("name") if isinstance(_rec, dict) else None
        if _name in CHAMPIONS:
            CHAMPIONS[_name].setdefault("class", (_rec.get("class") or ""))
            CHAMPIONS[_name].setdefault("role", (_rec.get("role") or ""))


def _last_number(value, default: float = 0.0) -> float:
    """Per-rank fields arrive as a scalar, a list of rank values, or a level
    range ({"lvlRange":[lo,hi]}) for values that scale with champion level.

    The top end is the honest reading for a finished build in every shape, and
    it keeps a list or dict from reaching float() and taking the whole profile
    down. Without the dict case a level-scaling ratio silently read as 0 and
    vanished from the champion's scaling profile.
    """
    if isinstance(value, dict):
        value = value.get("lvlRange") or []
    if isinstance(value, (list, tuple)):
        numbers = [v for v in value if isinstance(v, (int, float))]
        return float(numbers[-1]) if numbers else default
    return float(value) if isinstance(value, (int, float)) else default


# --------------------------------------------------------------------------
# ability text: normalisation and artifact detection
# --------------------------------------------------------------------------

# Patterns that mean the scraper produced something the model should not be
# asked to reason about. Deliberately narrow: a false positive here costs us a
# log line, but a pattern broad enough to match healthy text would hide real
# damage. As of the 7.2 data exactly one ability roster-wide trips these
# (Hecarim's Warpath), so this is a guard for future scrapes, not a bulk fixer.
_ARTIFACTS: dict[str, re.Pattern] = {
    "zero-equals": re.compile(r"\b0\s*="),
    "bare-equals": re.compile(r"\b\d+(?:\.\d+)?\s*=\s*\("),
    "empty-parens": re.compile(r"\(\s*\)"),
    "unresolved-brace": re.compile(r"[{}]"),
    "placeholder": re.compile(r"@\w+@|\$\{|\bNaN\b|\bundefined\b"),
    "dangling-operator": re.compile(r"[+\-*/]\s*\)"),
}

# `0 = (12% bonus MS)` is a failed numeric substitution: the scraper resolved the
# flat term to 0 and left the equals sign. Dropping the dead "0 = " keeps the
# meaning (the parenthesised ratio IS the whole value) without inventing one.
_DEAD_ASSIGNMENT = re.compile(r"\b0\s*=\s*(?=\()")


def ability_artifacts(champion: str) -> list[str]:
    """Suspicious ability text, as human-readable diagnostics. Never raises."""
    found = []
    abilities = (CHAMPIONS.get(champion) or {}).get("abilities") or []
    for ability in abilities:
        text = ability.get("text") or ""
        for label, pattern in _ARTIFACTS.items():
            if pattern.search(text):
                found.append(
                    f"{champion} [{ability.get('slot')}] {ability.get('name')}: "
                    f"{label} in {text[:90]!r}"
                )
        corrected = _ability_correction(champion, ability)
        if "cooldowns" in corrected:
            raw = _raw_cooldown_values(ability)
            fixed = _cooldown_values(ability, champion)
            if raw != fixed:
                found.append(
                    f"{champion} [{ability.get('slot')}] {ability.get('name')}: "
                    f"curated cooldown correction {raw!r} -> {fixed!r}"
                )
    # A different failure mode, and a worse one: the scrape returned the short
    # blurb instead of the real tooltip, so there are no numbers and no
    # cooldowns anywhere in the kit. Cho'Gath is the current example. Nothing
    # downstream can derive scaling from this, and the model must be told the
    # champion data is thin rather than left to invent the missing detail.
    # Judge on the four cast abilities, not the passive: a passive often carries
    # a level range ("40 - 82 Health") while every real tooltip is missing, which
    # is exactly how Cho'Gath presents.
    # Cooldowns are the reliable tell. Prose can still contain a stray number
    # ("Maximum 6 growths") while carrying no real tooltip, but a genuine scrape
    # always yields numeric cooldowns on the cast abilities.
    basics = [a for a in abilities if str(a.get("slot")) in {"1", "2", "3", "4"}]
    if basics and not any(_cooldown_values(a, champion) for a in basics):
        found.append(f"{champion}: no cast ability has a numeric cooldown -- the scrape "
                     "returned summary blurbs, not tooltips, so scaling and ability "
                     "timing are underivable for this champion")
    return found


def _clean_text(text: str) -> str:
    """Repair only what is provably broken; leave everything else alone.

    The rule is conservative on purpose: we remove a token that carries no
    meaning (`0 = ` before a parenthesised ratio) and normalise whitespace. We
    do not rewrite a formula we merely find surprising, because a wrong rewrite
    would be presented to the model as fact.
    """
    return " ".join(_DEAD_ASSIGNMENT.sub("", text or "").split())


# --------------------------------------------------------------------------
# ratios: what the kit actually scales on, weighted by how often it happens
# --------------------------------------------------------------------------

# Canonical stat names. The raw text is inconsistent ("AD", "Attack Damage",
# "bonus AD"), and the parsed formulas use their own vocabulary; both funnel here.
_STAT_CANON = {
    "ad": "totalAD", "attack damage": "totalAD", "total ad": "totalAD",
    "bonus ad": "bonusAD", "bonusad": "bonusAD",
    "ap": "AP", "ability power": "AP",
    "hp": "bonusHealth", "health": "bonusHealth", "bonus health": "bonusHealth",
    "bonus hp": "bonusHealth", "maxhp": "maxHealth", "max health": "maxHealth",
    "maximum health": "maxHealth", "targetmaxhp": "targetMaxHealth",
    "armor": "armor", "bonus armor": "armor",
    "mr": "magicResist", "magic resist": "magicResist",
    "ms": "movementSpeed", "movement speed": "movementSpeed", "bonusms": "movementSpeed",
    "attackspeed": "attackSpeed", "attack speed": "attackSpeed",
    "crit": "crit", "critchance": "crit",
}

_TEXT_RATIO = re.compile(
    r"\+\s*(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(bonus\s+|total\s+|max(?:imum)?\s+)?"
    r"(AD|AP|Attack Damage|Ability Power|Health|HP|Armor|Magic Resist|MS|Movement Speed)",
    re.IGNORECASE,
)

# A passive has no cooldown but is always available. Treating it as a 6-second
# effect keeps it meaningful without letting it dominate a kit's whole profile.
_PASSIVE_EQUIVALENT_CD = 6.0
# Below this, a cooldown is almost certainly a per-auto or per-tick figure and
# dividing by it would inflate the weight absurdly.
_MIN_CD = 1.0


# A percent of the TARGET's health is not the same currency as a percent of your
# own AD or AP, so target-relative ratios are scaled into comparable damage
# before they are weighted against each other. The factor is the reference
# health bar divided by the reference own-stat: a level-13 bruiser target around
# 3,400 HP against roughly 300 AD/AP on a finished build. Current-health and
# missing-health ratios pay out on part of that bar rather than all of it, so
# they get a share of the same factor.
_REFERENCE_TARGET_HP = 3400.0
_REFERENCE_OWN_STAT = 300.0
_MAX_HP_SCALE = _REFERENCE_TARGET_HP / _REFERENCE_OWN_STAT
_TARGET_SCALE = {
    "targetMaxHealth": _MAX_HP_SCALE,
    "targetCurrentHealth": _MAX_HP_SCALE * 0.7,
    "targetMissingHealth": _MAX_HP_SCALE * 0.3,
}


@dataclass
class Ratio:
    """One scaling ratio, with everything needed to weight it by real usage."""
    stat: str
    pct: float
    hits: int = 1
    cooldown: float = _PASSIVE_EQUIVALENT_CD
    slot: str = "?"
    per_auto: bool = False
    source: str = "text"

    @property
    def casts_per_minute(self) -> float:
        return 60.0 / max(_MIN_CD, self.cooldown)

    @property
    def weight(self) -> float:
        """Ratio percentage delivered per minute of uptime.

        This is the whole point of the module: it is what separates a 110% AD
        ratio on a 4-second ability from a 100% AP ratio on an 85-second
        ultimate. Both read as "scales with" in the old tags; here the first is
        worth roughly 20x the second.

        Target-relative ratios are converted first. "11% of the target's maximum
        Health" and "65% AD" are both stored as a percent, but they are percents
        of different things: one of a 3,400 HP health bar, the other of roughly
        300 attack damage. Adding them raw made Vayne's Silver Bolts -- her
        entire anti-tank identity -- read as 1.7% of her scaling and get labelled
        not_viable, and it did the same to 41 other champions.
        """
        return self.casts_per_minute * self.pct * _TARGET_SCALE.get(self.stat, 1.0) * max(1, self.hits)


def _ability_correction(champion: str, ability: dict) -> dict:
    """Reviewed correction for one ability, keyed by its stable slot.

    Corrections are deliberately external to the scraped champion record. This
    keeps the raw evidence auditable while ensuring every consumer (ratio
    weighting and prompt display) sees the same corrected value.
    """
    corrections = (OVERRIDES.get(champion) or {}).get("abilityDataCorrections") or {}
    return corrections.get(str(ability.get("slot") or "")) or {}


def _numeric_cooldowns(value) -> list[float]:
    values = []
    for entry in value or []:
        try:
            values.append(float(str(entry).strip()))
        except (TypeError, ValueError):
            continue
    return values


def _raw_cooldown_values(ability: dict) -> list[float]:
    """Numeric raw cooldowns only. Some scrapes yield ['', '', '']."""
    return _numeric_cooldowns(ability.get("cooldowns"))


def _cooldown_values(ability: dict, champion: str = "") -> list[float]:
    correction = _ability_correction(champion, ability) if champion else {}
    source = correction.get("cooldowns", ability.get("cooldowns"))
    return _numeric_cooldowns(source)


def _cooldown(ability: dict, champion: str = "") -> float:
    """Max-rank cooldown, which is the one a finished build actually plays at."""
    values = _cooldown_values(ability, champion)
    return values[-1] if values else _PASSIVE_EQUIVALENT_CD


def _ratios_from_formulas(champion: str) -> list[Ratio]:
    """Parsed ratios: hit counts and per-auto flags make these strictly better."""
    out: list[Ratio] = []
    abilities = (FORMULAS.get(champion) or {}).get("abilities") or {}
    for slot, ability in abilities.items():
        correction = ((OVERRIDES.get(champion) or {}).get("abilityDataCorrections") or {}).get(
            str(slot), {})
        cds = _numeric_cooldowns(correction.get("cooldowns", ability.get("cooldowns")))
        cooldown = cds[-1] if cds else _PASSIVE_EQUIVALENT_CD
        for dmg in ability.get("damage") or []:
            per_auto = str(dmg.get("when") or "") == "per auto"
            for ratio in dmg.get("ratios") or []:
                stat = _STAT_CANON.get(str(ratio.get("stat", "")).lower())
                pct = _last_number(ratio.get("pct"))
                if not stat or pct <= 0:
                    continue
                # hits is per-rank wherever the count scales (Miss Fortune's
                # ult is "12 / 14 / 16 waves"), so it gets the same max-rank
                # reading as every other rank field. int() on the raw value
                # crashed the whole roster's profile derivation.
                out.append(Ratio(
                    stat=stat, pct=pct, hits=max(1, int(_last_number(dmg.get("hits"), 1))),
                    cooldown=cooldown, slot=slot, per_auto=per_auto, source="formulas",
                ))
    return out


def _ratios_from_text(champion: str) -> list[Ratio]:
    out: list[Ratio] = []
    for ability in (CHAMPIONS.get(champion) or {}).get("abilities") or []:
        text = _clean_text(ability.get("text") or "")
        cooldown = _cooldown(ability, champion)
        for match in _TEXT_RATIO.finditer(text):
            pct = float(match.group(1))
            qualifier = (match.group(2) or "").strip().lower()
            raw_stat = match.group(3).strip().lower()
            key = f"{qualifier} {raw_stat}".strip() if qualifier else raw_stat
            stat = _STAT_CANON.get(key) or _STAT_CANON.get(raw_stat)
            if not stat:
                continue
            out.append(Ratio(
                stat=stat, pct=pct, cooldown=cooldown,
                slot=str(ability.get("slot") or "?"), source="text",
            ))
    return out


def ratios(champion: str) -> list[Ratio]:
    """Best available ratios: parsed where we have them, text everywhere else."""
    parsed = _ratios_from_formulas(champion)
    return parsed if parsed else _ratios_from_text(champion)


def steroids(champion: str) -> list[dict]:
    """Stat conversions and self-buffs, e.g. Hecarim turning move speed into AD.

    Only the parsed source carries these, which is fine: they are the signal
    that most needs to be exact, and guessing one from prose would be worse
    than not having it.
    """
    out = []
    for slot, ability in ((FORMULAS.get(champion) or {}).get("abilities") or {}).items():
        for steroid in ability.get("steroids") or []:
            entry = {"slot": slot, "ability": ability.get("name", ""), **steroid}
            out.append(entry)
    return out


# --------------------------------------------------------------------------
# scaling profile
# --------------------------------------------------------------------------

# Share of the kit's total ratio-weight, mapped to a label. The bands are the
# one genuinely arbitrary choice in this module, so they are stated once, here,
# rather than scattered through the code.
_SCALING_BANDS: list[tuple[float, str]] = [
    (0.40, "core"),
    (0.25, "high"),
    (0.12, "medium"),
    (0.04, "low"),
    (0.0, "low-incidental"),
]

# A cooldown at or above this is an ultimate or a once-a-fight effect. A stat
# whose weight comes almost entirely from such abilities is not a build path,
# however large the printed ratio is.
_ULT_CD = 60.0

# A stat can carry a real share of a kit's ratios without being something you
# should BUILD for -- Hecarim's W has 20% AP on each of 8 ticks, which is a
# quarter of his ratio weight and still does not make him an AP champion. So
# "does this stat appear" and "can this stat anchor a build" are answered
# separately: a stat anchors a build only if it dominates outright, or if it
# carries a solid share AND matches the kit's own damage identity.
_BUILD_PATH_SHARE = 0.35
_IDENTITY_SHARE = 0.15
# Genuine hybrids (Jax, Akali) have a second stat that is plainly comparable to
# their dominant one. An absolute threshold alone puts them on a knife edge --
# Jax's AD sits at 0.33 against a 0.35 cut-off -- so a stat also anchors when it
# is at least half the weight of the biggest one.
_RELATIVE_PATH_SHARE = 0.50
_IDENTITY_STATS = {
    "physical": {"totalAD", "bonusAD"},
    "magic": {"AP"},
}
# The three damage stats. An "off-identity" damage stat is one the champion's
# primary damage type is NOT (AP on a physical champion, or AD on a magic one).
_DAMAGE_STATS = {"totalAD", "bonusAD", "AP"}

# Champions with a genuinely playable second damage path in Wild Rift. Only for
# these may an OFF-IDENTITY damage stat rise above "not_viable" -- and even then
# only to "hybrid_or_experimental", never to a trusted "core"/"secondary"
# anchor. This is the same curated set the advisor uses for the AD/AP damage
# path, kept here so classification and itemisation agree. It exists because one
# incidental ability ratio (Fiora's Riposte carries +100% AP) otherwise made an
# AD duelist read as an AP champion.
HYBRID_DAMAGE_CHAMPIONS = {
    "Akali", "Corki", "Ezreal", "Jax", "Kai'Sa", "Katarina", "Kayle",
    "Shyvana", "Teemo", "Twitch", "Varus", "Volibear", "Warwick",
}


def build_identity(champion: str) -> str:
    """The champion's BUILD damage identity: "physical" or "magic".

    NOT the same as the scraped `primaryDamage`, which counts how many abilities
    deal physical vs magic damage and therefore mislabels AD bruisers whose
    passive or ult happens to deal magic (Irelia and Jax both scrape as
    'magic', though both are built AD). Build identity is what you ITEMISE for,
    and the reliable signals for that are class and `scalesWith`:

      - a curated override wins (for the genuine exceptions like AP bruisers);
      - Mage / Enchanter build AP;
      - a kit that scales with no AD at all (only AP) builds AP;
      - everything else builds AD.
    """
    record = CHAMPIONS.get(champion) or {}
    override = (OVERRIDES.get(champion) or {}).get("buildIdentity")
    if override in ("physical", "magic"):
        return override
    champ_class = record.get("class", "")
    if champ_class in ("Mage", "Enchanter"):
        return "magic"
    scales = set(record.get("scalesWith") or [])
    if scales and not (scales & {"ad", "bonusAd"}):
        return "magic"
    if scales & {"ad", "bonusAd"}:
        return "physical"
    return record.get("primaryDamage") or "physical"


_RANGED_CLASSES = {"Marksman", "Mage", "Enchanter"}

# Champions for whom Poke is not a playable build. Lives in playstyles.json
# because the studio filters its playstyle menu from the same list, and the two
# must not drift; tests/test_playstyles.py fails if they do.
_PLAYSTYLES_PATH = ROOT / "web-next" / "src" / "data" / "playstyles.json"
NO_POKE: set[str] = set(
    (json.loads(_PLAYSTYLES_PATH.read_text(encoding="utf-8")).get("noPoke") or [])
    if _PLAYSTYLES_PATH.exists() else []
)


def range_profile(champion: str) -> str:
    """"ranged" or "melee". Curated overrides win (the scrape has no range
    field); otherwise ranged classes are ranged and everyone else is melee."""
    override = (OVERRIDES.get(champion) or {}).get("rangeProfile")
    if override in ("ranged", "melee"):
        return override
    champ_class = (CHAMPIONS.get(champion) or {}).get("class", "")
    return "ranged" if champ_class in _RANGED_CLASSES else "melee"


def poke_eligibility(champion: str) -> dict:
    """Whether a Poke build is credible for this champion, with a reason.

    Poke means repeatable, reasonably safe ranged pressure BEFORE committing --
    not "has one ranged ability". A melee diver whose ranged spell is all-in
    setup (Akali) does not qualify; a ranged control mage does.

    The per-champion classification wins, because being ranged turned out not to
    be the test. Lillia, Thresh, Rakan and Vladimir all have ranged basic
    attacks and all fight at short range with almost none of their damage coming
    from range, so deriving Poke from the attack type answered the wrong
    question. The list is in playstyles.json, classified by
    scripts/classify_range.py, and is shared with the studio so both agree.
    """
    if champion in NO_POKE:
        return {"eligible": False,
                "reason": "Classified as unable to poke: this champion fights at short "
                          "range, whatever its basic attack range says."}
    if range_profile(champion) == "melee":
        return {"eligible": False,
                "reason": "Melee champion: its ranged abilities are engage/all-in setup, "
                          "not repeatable safe pressure from range."}
    if build_identity(champion) != "magic" and (CHAMPIONS.get(champion) or {}).get("class") != "Marksman":
        return {"eligible": False,
                "reason": "No sustained ranged-ability damage to poke with."}
    combat = combat_profile(champion)
    if combat.get("basicAttackPattern") == "basic-attack-carry":
        return {"eligible": False,
                "reason": "Auto-attack carry: pressure comes from sustained attacks, not poke."}
    return {"eligible": True,
            "reason": "Ranged kit with repeatable ability pressure before committing."}


def _label(share: float) -> str:
    if share <= 0:
        return "none"
    for threshold, name in _SCALING_BANDS:
        if share >= threshold:
            return name
    return "low-incidental"


def scaling_profile(champion: str) -> dict:
    """Labelled scaling per stat, plus normalised weights when derivable.

    Returns a dict with `scalingProfile` always, and `effectiveScalingWeights`
    only when there were ratios to weight. The label answers "how much of this
    kit's output rides on this stat", which is a different and more useful
    question than the old `scalesWith` list's "does this stat appear anywhere".
    """
    override = (OVERRIDES.get(champion) or {}).get("scalingProfile")
    rows = ratios(champion)
    totals: dict[str, float] = {}
    ult_only: dict[str, float] = {}
    for ratio in rows:
        totals[ratio.stat] = totals.get(ratio.stat, 0.0) + ratio.weight
        if ratio.cooldown >= _ULT_CD:
            ult_only[ratio.stat] = ult_only.get(ratio.stat, 0.0) + ratio.weight

    identity = _IDENTITY_STATS.get(build_identity(champion), set())

    grand = sum(totals.values())
    profile: dict[str, str] = {}
    weights: dict[str, float] = {}
    build_paths: list[str] = []
    notes: list[str] = []
    if grand > 0:
        top_share = max(totals.values()) / grand
        for stat, weight in sorted(totals.items(), key=lambda kv: -kv[1]):
            share = weight / grand
            label = _label(share)
            anchors = (share >= _BUILD_PATH_SHARE
                       or (share >= _IDENTITY_SHARE and stat in identity)
                       or share >= _RELATIVE_PATH_SHARE * top_share)
            # A stat carried almost entirely by a long-cooldown ability gets its
            # label held down: the ratio is real, the build path is not.
            if ult_only.get(stat, 0.0) / weight >= 0.7:
                anchors = False
                notes.append(f"{stat} scaling sits almost entirely on a long-cooldown "
                             "ability, so it is not repeatable damage")
            if anchors:
                build_paths.append(stat)
            elif label in ("core", "high", "medium"):
                # The ratio is genuinely there, so we do not zero it -- but it
                # must not read as an invitation to itemise for the stat.
                notes.append(f"{stat} carries {round(share * 100)}% of the ratio weight but "
                             "does not anchor a build path for this kit")
                label = "low-incidental"
            profile[stat] = label
            weights[stat] = round(share, 3)

    # Movement speed and attack speed rarely appear as damage ratios but often
    # appear as conversions, which is exactly the Hecarim case. Fold them in.
    for steroid in steroids(champion):
        stat = _STAT_CANON.get(str(steroid.get("stat", "")).lower())
        source = _STAT_CANON.get(str(steroid.get("from", "")).lower())
        if source and stat:
            profile.setdefault(source, "high")
            notes.append(f"{source} converts directly into {stat} "
                         f"({steroid.get('pct', '?')}%), so it is offensive stat, not just utility")

    # DAMAGE IDENTITY GATE. An off-identity damage stat (AP on an AD champion,
    # AD on a mage) must never anchor a trusted build, however large its raw
    # ratio -- a single ability ratio is not a build path. It can rise to
    # "hybrid_or_experimental" only for a curated genuine hybrid; otherwise it is
    # not_viable. The champion's OWN damage identity is protected the other way:
    # if it has any real weight it stays at least a secondary path.
    primary = build_identity(champion)
    identity_stats = _IDENTITY_STATS.get(primary, set())
    off_identity = _DAMAGE_STATS - identity_stats if identity_stats else set()
    is_hybrid = champion in HYBRID_DAMAGE_CHAMPIONS
    damage_identity_note = False
    for stat in list(off_identity):
        if stat in build_paths:
            build_paths.remove(stat)
            damage_identity_note = True
    if damage_identity_note:
        kind = "AP" if "AP" in off_identity else "AD"
        notes.append(f"{kind} appears in the ratios but this kit's damage identity is "
                     f"{primary}; off-identity damage cannot anchor a trusted build"
                     + (" (hybrid champion: usable only as an experimental path)"
                        if is_hybrid else ""))

    if override:
        profile.update(override)
        notes.append("curated override applied")

    result: dict = {"scalingProfile": profile}
    if weights:
        result["effectiveScalingWeights"] = weights
    if build_paths:
        result["buildPathStats"] = build_paths
    if notes:
        result["scalingNotes"] = sorted(set(notes))

    # Normalised viability map (build-system plan Part 1.5). It separates the raw
    # ratio share (a number that says how much of the kit's output touches a
    # stat) from BUILD-PATH VIABILITY (whether you can itemise for it at all).
    # The two were conflated: a stat could read 0.26 of the ratio weight AND be
    # "low-incidental", which sends conflicting signals. Viability takes
    # precedence, and the prompt is told so.
    if weights:
        result["rawRatioShare"] = weights
    if profile:
        viability = {}
        for stat, label in profile.items():
            if stat in _TARGET_SCALE:
                # Not a build path in either direction: no item sells "percent
                # of the enemy's health". Listing it as not_viable told the
                # model to ignore Vayne's anti-tank identity; it belongs in the
                # scaling picture instead, which rawRatioShare now carries.
                continue
            if stat in off_identity:
                # Off-identity damage: experimental-only for real hybrids, else
                # not usable. Never a trusted anchor.
                viability[stat] = "hybrid_or_experimental" if is_hybrid else "not_viable"
            elif stat in build_paths:
                viability[stat] = "core" if label == "core" else "secondary"
            elif stat in identity_stats and label not in ("none",):
                # The champion's own damage stat is at least a secondary path
                # even if a rogue off-identity ratio out-weighed it.
                viability[stat] = "secondary"
            elif label in ("medium",):
                viability[stat] = "secondary"
            else:  # low, low-incidental, none
                viability[stat] = "not_viable"

        # A champion must be buildable for SOMETHING. If the identity gate left
        # nothing "core" (the AD ratios were under-captured in the scrape, as for
        # Fiora), promote the strongest identity damage stat -- never an
        # off-identity one -- so the kit still has a trusted anchor.
        if identity_stats and not any(v == "core" for v in viability.values()):
            present = [s for s in identity_stats if s in weights]
            if present:
                top = max(present, key=lambda s: weights.get(s, 0.0))
                viability[top] = "core"
                if top not in build_paths:
                    build_paths.append(top)
            elif not viability:
                # Nothing measurable is buildable. K'Sante reaches here: he
                # scales off armour, magic resist and target health, so there is
                # no AD or AP ratio to read, and build_identity mislabels him
                # magic as a result while every damage component he has is
                # physical. Trust the scraped damage type over the derived
                # identity in that case, and say the anchor is inferred.
                primary = (CHAMPIONS.get(champion) or {}).get("primaryDamage")
                top = ("AP" if primary == "magic"
                       else "totalAD" if primary == "physical"
                       else sorted(identity_stats)[0])
                viability[top] = "core"
                build_paths.append(top)
                result.setdefault("scalingNotes", []).append(
                    f"no buildable ratio survived extraction for this kit, so {top} is taken "
                    "from the champion's damage identity rather than measured. Treat it as a "
                    "floor, not evidence.")

        target_rel = [s for s in profile if s in _TARGET_SCALE]
        if target_rel:
            result.setdefault("scalingNotes", []).append(
                f"{', '.join(target_rel)} is real damage but not a build path: no item grants "
                "it. Treat it as what this kit does to high-health targets, and as a reason "
                "to buy what makes the ability land more often, not as a stat to itemise for.")
        result["buildPathViability"] = viability
    if build_paths:
        result["buildPathStats"] = build_paths  # may have gained the promoted stat
    return result


# --------------------------------------------------------------------------
# combat profile
# --------------------------------------------------------------------------

# Text that means "this ability empowers ONE attack" -- a spellblade trigger and
# a weaving signal, but NOT evidence of repeated on-hit application. Separating
# these two readings is the entire reason the old `onHit` tag misfires.
_SINGLE_EMPOWER = re.compile(
    r"next (?:basic )?attack|next attack|empowere?d? (?:basic )?attack|"
    r"his next attack|her next attack|their next attack",
    re.IGNORECASE,
)
# A proc that fires ONCE per target (or on a per-target cooldown) is not
# repeated on-hit, however fast the champion attacks. Jarvan's passive -- "the
# first attack against an enemy ... cooldown per unique enemy" -- is the case
# that made an engage bruiser read as an on-hit carry.
_ONCE_PER_TARGET = re.compile(
    r"first (?:basic )?attack|once per|per unique|cooldown per|per target|"
    r"each unique enemy",
    re.IGNORECASE,
)
# Text that means on-hit effects land REPEATEDLY: an explicit every-hit /
# every-Nth-hit mechanic, a sustained attack window, or stacking attack speed.
# Deliberately NOT "attacks against" / "attacks gain" -- those matched
# once-per-target procs and single empowered hits.
_REPEATED_ATTACKS = re.compile(
    r"attacks? (?:for|over) the next|basic attacks (?:deal|apply|grant)|"
    r"for (?:the )?(?:next )?\d+ (?:seconds|s)[^.]{0,40}attack speed|"
    r"每|stacking attack speed|each attack|every attack|every \d+(?:st|nd|rd|th)? "
    r"(?:basic )?attack|on-hit",
    re.IGNORECASE,
)
_ATTACK_SPEED_STEROID = re.compile(r"attack speed", re.IGNORECASE)

_LEVELS = ("none", "low", "medium", "high")


def _kit_text(champion: str) -> str:
    return " ".join(
        _clean_text(a.get("text") or "")
        for a in (CHAMPIONS.get(champion) or {}).get("abilities") or []
    )


def _min_basic_cooldown(champion: str) -> float:
    """Shortest non-ultimate cooldown: how tightly the kit can weave attacks."""
    cds = [
        _cooldown(a, champion)
        for a in (CHAMPIONS.get(champion) or {}).get("abilities") or []
        if str(a.get("slot")) in {"1", "2", "3"} and a.get("cooldowns")
    ]
    return min(cds) if cds else _PASSIVE_EQUIVALENT_CD


def combat_profile(champion: str) -> dict:
    """How the champion actually fights, in terms an item audit can use.

    Every field is derived from the ability text, the parsed formulas, or the
    curated archetype file -- never from the coarse `mechanics` tags, which is
    the point. A curated override in data/combat_profiles.json wins outright.
    """
    champ = CHAMPIONS.get(champion) or {}
    text = _kit_text(champion)
    archetype = (ARCHETYPES.get(champion) or {}).get("archetype", "")
    auto_share = (ARCHETYPES.get(champion) or {}).get("autoShare")
    champ_class = champ.get("class", "")
    rows = ratios(champion)
    per_auto = [r for r in rows if r.per_auto]
    min_cd = _min_basic_cooldown(champion)

    repeated = bool(_REPEATED_ATTACKS.search(text))
    once_per_target = bool(_ONCE_PER_TARGET.search(text))
    # A once-per-target proc reads as a single empowered attack, NOT repeated
    # application -- unless the kit ALSO has genuine every-hit wording.
    single_empower = bool(_SINGLE_EMPOWER.search(text)) or (once_per_target and not repeated)
    attack_speed_steroid = any(
        _STAT_CANON.get(str(s.get("stat", "")).lower()) == "attackSpeed"
        for s in steroids(champion)
    ) or bool(re.search(r"gains? [^.]{0,30}attack speed", text, re.IGNORECASE))

    # --- basic attack pattern -------------------------------------------------
    # Ordering matters: a champion can trip several of these, and the first
    # match is the most specific reading of the kit. An attack-speed steroid
    # alone no longer forces "repeated-attacks": it must be paired with genuine
    # repeated-application wording, and NOT be a once-per-target proc (Jarvan).
    if archetype == "autoattacker" or champ_class == "Marksman":
        pattern = "basic-attack-carry"
    elif archetype == "onhitcaster" or (attack_speed_steroid and repeated and not once_per_target):
        pattern = "repeated-attacks"
    elif archetype == "weaver" or (single_empower and min_cd <= 8.0):
        pattern = "ability-weaving"
    elif archetype == "spellcaster":
        pattern = "caster"
    elif per_auto:
        pattern = "ability-weaving"
    elif single_empower or repeated:
        pattern = "mixed"
    else:
        pattern = "caster"

    # --- basic attack frequency ----------------------------------------------
    if auto_share is not None:
        frequency = _LEVELS[min(3, max(0, int(round(float(auto_share) * 3))))]
    elif pattern in ("basic-attack-carry", "repeated-attacks"):
        frequency = "high"
    elif pattern == "ability-weaving":
        frequency = "medium"
    else:
        frequency = "low"

    # --- spellblade reliability ----------------------------------------------
    # Spellblade wants ability casts followed by an attack. A short basic
    # cooldown supplies the casts; an empowered-attack line supplies the intent.
    if pattern == "caster" and frequency == "low":
        spellblade = "low"
    elif single_empower and min_cd <= 6.0:
        spellblade = "high"
    elif pattern in ("ability-weaving", "repeated-attacks", "basic-attack-carry"):
        spellblade = "high" if min_cd <= 8.0 else "medium"
    else:
        spellblade = "medium" if min_cd <= 10.0 else "low"

    # --- repeated on-hit reliance --------------------------------------------
    # THE distinction the old tag could not make. One empowered attack -- or a
    # once-per-target proc -- is not on-hit reliance, however much attack speed
    # the kit carries. High reliance needs genuine repeated application.
    if once_per_target and not repeated:
        # A per-target proc (Jarvan) plus an attack-speed steroid is still low
        # reliance: the on-hit effect does not scale with attacks-per-second.
        on_hit = "low"
    elif pattern == "basic-attack-carry":
        on_hit = "high"
    elif pattern == "repeated-attacks":
        on_hit = "high" if attack_speed_steroid else "medium"
    elif single_empower and not attack_speed_steroid:
        on_hit = "low"
    elif repeated and attack_speed_steroid:
        on_hit = "medium"
    else:
        on_hit = "none" if pattern == "caster" else "low"

    # --- attack speed and crit value -----------------------------------------
    attack_speed_value = {
        "basic-attack-carry": "high", "repeated-attacks": "high",
        "ability-weaving": "low", "mixed": "medium", "caster": "none",
    }[pattern]
    if attack_speed_steroid and attack_speed_value in ("none", "low"):
        attack_speed_value = "medium"
    # Crit is only worth stacking where attacks are the damage. A kit whose
    # damage is abilities gets nothing from crit chance no matter its class.
    crit_value = "high" if pattern == "basic-attack-carry" else (
        "medium" if pattern == "repeated-attacks" else "low"
    )
    if champ_class in ("Mage", "Support") or pattern == "caster":
        crit_value = "none"

    # --- mobility-to-damage conversion ---------------------------------------
    conversions = {
        _STAT_CANON.get(str(s.get("from", "")).lower()) for s in steroids(champion)
    }
    if "movementSpeed" in conversions:
        mobility_damage = "high"
    elif re.search(r"movement speed", text, re.IGNORECASE) and pattern != "caster":
        mobility_damage = "medium"
    else:
        mobility_damage = "low"

    # --- healing reliance -----------------------------------------------------
    heal_hits = len(re.findall(r"heal|restore|lifesteal|omnivamp|life steal",
                               text, re.IGNORECASE))
    healing = "high" if heal_hits >= 4 else "medium" if heal_hits >= 2 else (
        "low" if heal_hits else "none")

    profile = {
        "basicAttackPattern": pattern,
        "basicAttackFrequency": frequency,
        "spellbladeProcReliability": spellblade,
        "repeatedOnHitReliance": on_hit,
        "attackSpeedValue": attack_speed_value,
        "critValue": crit_value,
        "mobilityToDamageConversion": mobility_damage,
        "healingReliance": healing,
    }
    profile.update((OVERRIDES.get(champion) or {}).get("combatProfile") or {})
    return profile


_ENGINE_BY_PATTERN = {
    "basic-attack-carry": "Sustained basic attacks are the repeatable combat engine.",
    "repeated-attacks": "Repeated empowered/on-hit attacks are the repeatable combat engine.",
    "ability-weaving": "Alternate short-cooldown abilities with basic attacks and proc effects.",
    "caster": "Repeated basic-ability casts are the combat engine; the ultimate is a spike, not the whole build.",
    "mixed": "Combine ability rotations with basic attacks; neither a single ratio nor the ultimate defines the build alone.",
}

_SOURCE_BY_PATTERN = {
    "basic-attack-carry": "basic attacks",
    "repeated-attacks": "repeated attacks and on-hit effects",
    "ability-weaving": "basic abilities woven with attacks",
    "caster": "basic abilities",
    "mixed": "basic abilities and attacks",
}


def build_identity_profile(champion: str) -> dict:
    """Reviewed/derived answer to *how this champion should be itemised*.

    Ratio shares remain useful evidence, but they cannot identify the ability or
    attack that actually carries a champion's fight pattern. This layer gives
    the generator a primary combat engine, main damage source and an explicit
    set of approved build paths. A small reviewed override wins where text
    derivation is known to be misleading (Rammus, Nasus, Fiora, Irelia, Nunu).
    """
    champ = CHAMPIONS.get(champion) or {}
    combat = combat_profile(champion)
    pattern = combat.get("basicAttackPattern", "mixed")
    damage_identity = build_identity(champion)
    champ_class = champ.get("class", "")
    role = champ.get("role", "")

    if champ_class == "Tank":
        primary_path = "tank"
        core_stats = ["health", "armor", "magicResist", "abilityHaste"]
        approved = ["tank"]
    elif champ_class == "Enchanter" and role == "Support":
        primary_path = "support"
        core_stats = ["abilityPower", "abilityHaste", "healShieldPower"]
        approved = ["support"]
    elif damage_identity == "magic":
        primary_path = "magic"
        core_stats = ["abilityPower", "abilityHaste", "magicPenetration"]
        approved = ["magic"]
    else:
        primary_path = "physical"
        core_stats = ["attackDamage", "abilityHaste", "physicalPenetration"]
        approved = ["physical"]

    secondary = []
    if combat.get("attackSpeedValue") in ("medium", "high"):
        secondary.append("attackSpeed")
    if combat.get("repeatedOnHitReliance") in ("medium", "high"):
        secondary.append("onHit")
    if combat.get("critValue") == "high":
        secondary.append("crit")
    if combat.get("healingReliance") in ("medium", "high"):
        secondary.append("sustain")

    result = {
        "damageIdentity": damage_identity,
        "primaryBuildPath": primary_path,
        "primaryCombatEngine": _ENGINE_BY_PATTERN.get(pattern, _ENGINE_BY_PATTERN["mixed"]),
        "mainDamageSource": _SOURCE_BY_PATTERN.get(pattern, _SOURCE_BY_PATTERN["mixed"]),
        "coreStats": core_stats,
        "secondaryStats": secondary,
        "approvedBuildPaths": approved,
        "forbiddenAnchors": ["AP"] if damage_identity == "physical" else ["AD"],
    }

    reviewed = (OVERRIDES.get(champion) or {}).get("buildIdentityProfile") or {}
    result.update(reviewed)

    explicit_alternative = (OVERRIDES.get(champion) or {}).get("alternativePath")
    if explicit_alternative:
        result["alternativePath"] = dict(explicit_alternative)
    elif champion in HYBRID_DAMAGE_CHAMPIONS:
        # This list is curated above. A printed off-stat ratio alone never gets
        # here, which is why Fiora/Irelia cannot accidentally become AP builds.
        result["alternativePath"] = {
            "id": "hybrid-ad-ap",
            "label": "Hybrid AD + AP",
            "description": "A genuine secondary hybrid path supported by repeatable AD and AP interactions in the kit.",
            "anchorStats": ["AD", "AP"],
        }
    return result


def alternative_path(champion: str) -> dict | None:
    """Credible optional path, or ``None`` when novelty would be forced."""
    path = build_identity_profile(champion).get("alternativePath")
    return dict(path) if isinstance(path, dict) and path.get("id") else None


def profile(champion: str, log: bool = True) -> dict:
    """Everything the prompt needs about how this champion fights and scales."""
    artifacts = ability_artifacts(champion)
    if log and artifacts:
        # stderr only: /api/build parses this process's stdout as JSON, so a
        # stray print here takes the live build tool down.
        for line in artifacts:
            print(f"[advisor] ability-text artifact: {line}", file=sys.stderr)
    out: dict = {"combatProfile": combat_profile(champion)}
    out.update(scaling_profile(champion))
    out["buildIdentityProfile"] = build_identity_profile(champion)
    out["rangeProfile"] = range_profile(champion)
    out["playstyleEligibility"] = {"poke": poke_eligibility(champion)}
    structured = structured_effects(champion)
    if structured:
        out["structuredEffects"] = structured
    if artifacts:
        out["abilityTextArtifacts"] = artifacts
    return out


# How a mechanic changes what is worth buying. The extraction records the
# mechanic; this says why the model should care, because "reload" on its own
# means nothing to a model deciding between two attack-speed items.
_MECHANIC_MEANING = {
    "fixedAttackSpeed": ("attack speed does NOT increase this champion's attack rate. "
                         "Buying attack speed for the sake of attacking faster is wasted gold"),
    "reload": ("attacks come in magazines with a reload between them, so attack speed "
               "buys less than the raw number suggests"),
    "multiShot": ("one basic attack fires several projectiles, so on-hit and per-hit "
                  "effects trigger more than once per attack"),
    "doubleShot": "attacks fire an extra shot under a condition, which multiplies on-hit effects",
    # Deliberately says nothing about attack speed: Jhin has this AND
    # fixedAttackSpeed, and claiming the empowered hit rewards attack speed
    # would contradict the line directly above it.
    "everyNHit": ("every Nth attack is empowered, so per-attack damage and on-hit effects "
                  "are worth more than they look on a flat damage comparison"),
    # Says STATS, not items, deliberately: an item's name is not its stat line,
    # and "mana items are dead" reads as a ban on anything named for mana even
    # when its actual stats are useful. No item is named here -- an earlier
    # version pointed at one as an example and a model took that as a
    # recommendation, buying it five times out of five.
    "noResource": ("this champion has NO mana, so mana, mana regeneration and mana-scaling "
                   "STATS are dead on it. Judge each item by its stat line rather than by "
                   "its name"),
    "transform": "the champion transforms, and the transformed state is not fully modelled here",
}


def kit_mechanics(champion: str) -> list[str]:
    """Kit facts that decide which STATS are worth buying.

    These are extracted per champion but were never reaching the prompt, so the
    model was choosing items for Jhin without being told that attack speed does
    nothing for him, and for Graves without being told he has no mana.
    """
    out: list[str] = []
    rec = FORMULAS.get(champion) or {}
    for mech in rec.get("mechanics") or []:
        kind = mech.get("kind")
        meaning = _MECHANIC_MEANING.get(kind)
        if not meaning:
            continue
        params = ", ".join(f"{k}={v}" for k, v in mech.items()
                           if k in ("magazine", "shots", "n", "secondShotPct")
                           and isinstance(v, (int, float)))
        out.append(f"{kind}{f' ({params})' if params else ''}: {meaning}.")
    know = rec.get("knowledge") or {}
    eff = know.get("asEfficiency")
    if isinstance(eff, (int, float)):
        out.append(
            f"attackSpeedEfficiency={eff:.2f} (1.0 = a normal marksman, lower means attack "
            f"speed converts poorly on this kit). ESTIMATED, not measured.")
    if know.get("abilitiesCanCrit") is False:
        out.append("this champion's ABILITIES cannot crit, so crit only improves basic attacks.")
    if know.get("resource") == "none" and not any(m.get("kind") == "noResource"
                                                  for m in rec.get("mechanics") or []):
        out.append("this champion uses no mana: mana and mana-scaling items are dead stats.")
    elif know.get("resource") == "energy":
        # The resource field has carried "energy" all along and nothing read it,
        # so the model was left to assume energy behaves like mana. It does not,
        # and the difference decides an item: cooldown reduction buys far less
        # here, because what stops an energy champion casting again is energy
        # regeneration, not the cooldown. Ionian Boots of Lucidity on Akali was
        # the case that exposed this -- graded a clear loss against a model that
        # happened to avoid them.
        said_no_mana = any(m.get("kind") == "noResource" for m in rec.get("mechanics") or [])
        out.append(
            ("" if said_no_mana else
             "this champion uses ENERGY, not mana, so mana and mana-regeneration stats "
             "are dead on it. ")
            + "ENERGY is a small fixed pool that does not grow with items and refills on "
              "its own schedule, so cooldown reduction / ability haste is worth materially "
              "less here than on a mana champion: what stops the next cast is energy, not "
              "the cooldown. Do not pick an item or boot mainly for haste on this kit.")
    return out


def structured_effects(champion: str) -> list[dict]:
    """Machine-readable effects that outrank the prose when the prose is broken.

    Hecarim's Warpath is the motivating case: its text arrives as
    "gains 0 = (12% bonus MS) Attack Damage", while the parsed formulas carry
    the same effect cleanly as a stat conversion. Where both exist the model is
    shown both, and told the structured one is authoritative.
    """
    # Per-rank steroids arrive as one entry per rank (Camille's Hookshot gives
    # four attack-speed rows, 50/60/70/80%). Keyed insertion keeps the LAST one
    # per effect, which is max rank -- what a finished build actually plays at.
    collapsed: dict[tuple, dict] = {}
    for steroid in steroids(champion):
        stat = _STAT_CANON.get(str(steroid.get("stat", "")).lower())
        source = _STAT_CANON.get(str(steroid.get("from", "")).lower())
        entry = {
            "ability": steroid.get("ability", ""),
            "slot": steroid.get("slot", "?"),
            "effectType": "stat-conversion" if source else "self-buff",
            "outputStat": stat or steroid.get("stat"),
        }
        pct = _last_number(steroid.get("pct"))
        if pct:
            entry["ratio"] = round(pct / 100.0, 4)
        flat = _last_number(steroid.get("flat"))
        if flat:
            entry["flat"] = flat
        if source:
            entry["inputStat"] = source
        if steroid.get("note"):
            entry["note"] = steroid["note"]
        collapsed[(steroid.get("slot"), steroid.get("ability"), stat, source)] = entry
    return list(collapsed.values())


def normalized_abilities(champion: str) -> list[dict]:
    """Ability records with the text cleaned, for prompt assembly."""
    out = []
    for ability in (CHAMPIONS.get(champion) or {}).get("abilities") or []:
        corrected = _ability_correction(champion, ability)
        out.append({
            "slot": ability.get("slot", "?"),
            "name": ability.get("name", ""),
            "text": _clean_text(ability.get("text") or ""),
            "cooldowns": corrected.get("cooldowns", ability.get("cooldowns") or []),
        })
    return out
