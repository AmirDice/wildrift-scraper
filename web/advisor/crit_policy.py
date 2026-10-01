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


def allows(champion: str, champion_class: str | None) -> bool:
    """Whether a champion may use a crit item in curated mode."""
    return not frontline(champion_class) or champion in STANDARD


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
    """Return a short, model-visible rule without exposing item names."""
    classes = champion_classes or []
    is_frontline = any(frontline(value) for value in classes)
    level = affinity(champion)
    if not is_frontline and level == "none":
        return ""
    if level == "strong":
        return ("  crit affinity: STRONG/CORE for this champion; a coherent crit "
                "path is a legitimate ranked build identity.")
    if level == "situational":
        return ("  crit affinity: SITUATIONAL/OFF-META; do not use a crit path in "
                "standard curated builds. It is available only in unrestricted "
                "mode when the player explicitly accepts the warning.")
    if is_frontline:
        return ("  crit policy: NOT A REVIEWED CRIT CHAMPION. Do not buy items whose "
                "defining stat/passive is critical strike; preserve this tank/bruiser "
                "identity unless the user explicitly enables unrestricted off-meta mode.")
    return ""
