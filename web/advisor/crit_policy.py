"""Reviewed critical-strike policy for frontline champion itemization.

Crit is a delivery path, not a generic AD upgrade.  This small, explicit
roster keeps the engine and the model from turning every bruiser/tank into a
mathematically attractive but ranked-impractical crit build.  The policy is
intentionally bypassed by unrestricted/off-meta mode.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


_DATA = Path(__file__).resolve().parents[2] / "data" / "champion_crit_affinity.json"
try:
    _STORE = json.loads(_DATA.read_text(encoding="utf-8"))
except (OSError, ValueError):
    _STORE = {"strong": [], "situational": [], "policy": ""}

STRONG = frozenset(str(name) for name in _STORE.get("strong") or [])
SITUATIONAL = frozenset(str(name) for name in _STORE.get("situational") or [])
# Situational entries are retained as research metadata, but they are not
# standard-build identities.  They belong behind the explicit unrestricted
# toggle so a mathematical crit shell cannot leak into normal recommendations.
ALL_REVIEWED = STRONG | SITUATIONAL
STANDARD = STRONG

# The frontend/catalog uses both Bruiser and Fighter/Juggernaut labels for the
# same close-range itemization family.  Garen is a Bruiser/Juggernaut in the
# curated metadata and has a reviewed crit affinity.
FRONTLINE_CLASSES = frozenset({"Tank", "Bruiser", "Fighter", "Juggernaut"})


def affinity(champion: str) -> str:
    if champion in STRONG:
        return "strong"
    if champion in SITUATIONAL:
        return "situational"
    return "none"


def frontline(champion_class: str | None) -> bool:
    return str(champion_class or "") in FRONTLINE_CLASSES


#: An item this share of a champion's top players build, in any region, is
#: not "never-build" for that champion whatever a reviewed list says.
LADDER_FLOOR = 0.10
_LADDER_FILES = ("ladder_consensus.json", "ladder_consensus_na.json",
                 "ladder_consensus_cn.json")
_LADDER: list[dict] | None = None


def _ladder_regions() -> list[dict]:
    """{champion: {slug: share}} per region, from the ladder consensus files."""
    global _LADDER
    if _LADDER is None:
        _LADDER = []
        for name in _LADDER_FILES:
            try:
                store = json.loads((_DATA.parent / name).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            store = store.get("champions", store) if isinstance(store, dict) else {}
            region: dict[str, dict[str, float]] = {}
            for champion, record in store.items():
                if not isinstance(record, dict):
                    continue
                shares = {}
                for row in record.get("items") or []:
                    slug, of = str(row.get("slug") or ""), row.get("of") or 0
                    if slug and of:
                        shares[slug] = max(shares.get(slug, 0.0), (row.get("count") or 0) / of)
                region[champion] = shares
            _LADDER.append(region)
    return _LADDER


def ladder_share(champion: str, slug: str) -> float:
    """The largest share of this champion's top players building `slug`."""
    base = champion.split(" (")[0]
    return max((region.get(base, {}).get(slug, 0.0) for region in _ladder_regions()),
               default=0.0)


def ladder_built(champion: str, slug: str) -> bool:
    return bool(champion) and ladder_share(champion, slug) >= LADDER_FLOOR


def ladder_crit_items(champion: str) -> list[str]:
    """Crit items at least LADDER_FLOOR of this champion's top players build."""
    from web.advisor.itemmeta import ITEMS
    base = champion.split(" (")[0]
    found: set[str] = set()
    for region in _ladder_regions():
        for slug, share in region.get(base, {}).items():
            if share >= LADDER_FLOOR and item_has_crit(ITEMS.get(slug)):
                found.add(slug)
    return sorted(found, key=lambda slug: -ladder_share(champion, slug))


def _card_forbids_crit(champion: str) -> bool:
    from web.advisor import prompt  # prompt imports this module
    limits = (prompt.identity_card(champion) or {}).get("hardLimits") or {}
    never = " ".join(str(row.get("path") or "") for row in limits.get("neverArchetypes") or []
                     if isinstance(row, dict)).lower()
    return "crit" in {str(s).lower() for s in limits.get("avoidStats") or []} or "crit" in never


def ladder_crit_path(champion: str) -> bool:
    """Do this champion's top players run a crit PATH, not one crit item?

    Two distinct crit items each built by a tenth of one region's ladder.
    Riven is the case that asked for it: NA's top 30 build Mortal Reminder
    (23%), Infinity Edge and Essence Reaver (10% each), and the reviewed list
    above did not have her at all, so every Riven build was told crit was
    never an option.
    """
    from web.advisor.itemmeta import ITEMS
    base = champion.split(" (")[0]

    def path_item(slug: str) -> bool:
        # Penetration items that happen to carry crit (Mortal Reminder, Lord
        # Dominik's, The Collector) are bought for the pen. Counting them made
        # Renekton and Darius "crit champions" off Mortal Reminder plus LDR.
        stats = (ITEMS.get(slug) or {}).get("stats") or {}
        return (item_has_crit(ITEMS.get(slug))
                and "physicalPen" not in stats and "physicalPenFlat" not in stats)

    # A reviewed card that rules crit out wins over the ladder: Darius's says
    # crit does nothing for his execute or bleed, and EU's Galeforce Darius
    # does not make that untrue. The player can still ask for crit by name.
    if _card_forbids_crit(base):
        return False
    for region in _ladder_regions():
        crit = [slug for slug, share in region.get(base, {}).items()
                if share >= LADDER_FLOOR and path_item(slug)]
        if len(crit) >= 2:
            return True
    return False


def allows(champion: str, champion_class: str | None) -> bool:
    """Whether a champion may use a crit item in curated mode."""
    return (not frontline(champion_class) or champion in STANDARD
            or ladder_crit_path(champion))


def item_has_crit(item: dict | None) -> bool:
    item = item or {}
    stats = item.get("stats") or {}
    passive_text = " ".join(str(line) for line in (item.get("passives") or []))
    return bool(
        "crit" in stats
        # Yun Tal and similar items can grant Critical Rate without carrying a
        # literal `crit` stat. Do not treat defensive wording such as
        # "critically struck" (Randuin's) or a one-off empowered attack
        # (Sundered Sky) as a crit item.
        or re.search(r"\b(?:critical|crit)\s+(?:rate|chance|damage)\b",
                     passive_text, re.I)
    )


def prompt_line(champion: str, champion_classes: list[str] | None = None) -> str:
    """Return a short, model-visible rule without exposing item names.

    Never says what is popular (owner's rule: the build model scores items on
    their merits). The ladder decides WHICH line a champion gets; the line
    itself only states what is and is not a legitimate path.
    """
    classes = champion_classes or []
    is_frontline = any(frontline(value) for value in classes)
    level = affinity(champion)
    if not is_frontline and level == "none":
        return ""
    if level == "strong":
        return ("  crit affinity: STRONG/CORE for this champion; a coherent crit "
                "path is a legitimate ranked build identity.")
    if ladder_crit_path(champion):
        return ("  crit affinity: VIABLE. A coherent crit path is a legitimate build "
                "for this champion, alongside its standard one.")
    # Single crit items bought for penetration or anti-heal are not a crit path.
    pen_note = (" Single crit items bought for their penetration or anti-heal are "
                "fine one at a time." if ladder_crit_items(champion) else "")
    if level == "situational":
        return ("  crit affinity: SITUATIONAL/OFF-META; do not use a crit path in "
                "standard curated builds. It is available only in unrestricted "
                "mode when the player explicitly accepts the warning." + pen_note)
    if is_frontline:
        if pen_note:
            return ("  crit policy: no crit PATH on this champion in a standard build."
                    + pen_note)
        return ("  crit policy: NOT A REVIEWED CRIT CHAMPION. Do not buy items whose "
                "defining stat/passive is critical strike; preserve this tank/bruiser "
                "identity unless the user explicitly enables unrestricted off-meta mode.")
    return ""
