"""Export the clean item DB to the frontend for the /items page.

Source: data/items.json (the scraped, patch-7.2 item DB, icons already rehosted
to /items/<slug>.webp). We copy the display fields and clean the passive text:
wr-meta embeds stat-icon markers like "[physicalVamp]" which we either drop
(when they're a leading icon before a number) or expand to words (inline refs).

Output: web-next/src/data/items.json

Run:
    python -m scripts.export_items
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "items.json"
OUT = ROOT / "web-next" / "src" / "data" / "items.json"


#: What a stat marker is called in a sentence. Without this, camelCase keys are
#: split into something close but wrong ("hp" -> "Hp", "crit" -> "Crit"), which
#: is how the site ended up printing "current Health Hp" and "35% Hp Health".
STAT_WORDS = {
    "hp": "Health", "hpRegen": "Health Regen", "ad": "Attack Damage",
    "ap": "Ability Power", "armor": "Armor", "mr": "Magic Resist",
    "attackSpeed": "Attack Speed", "crit": "Critical Rate",
    "abilityHaste": "Ability Haste", "moveSpeed": "Move Speed",
    "mana": "Mana", "manaRegen": "Mana Regen", "healShieldPower": "Heal and Shield Power",
    "physicalPen": "Armor Penetration", "physicalPenFlat": "Armor Penetration",
    "magicPen": "Magic Penetration", "magicPenFlat": "Magic Penetration",
    "physicalVamp": "Physical Vamp", "omnivamp": "Omnivamp", "lifesteal": "Lifesteal",
    "tenacity": "Tenacity",
}


#: The other ways a passive writes the same stat, so an icon beside one of
#: them still reads as a repeat ("Movement Speed [moveSpeed]").
SAME_AS = {
    "hp": ("Health", "max Health", "HP"),
    "ad": ("Attack Damage", "AD"),
    "ap": ("Ability Power", "AP"),
    "mr": ("Magic Resist", "Magic Resistance"),
    "moveSpeed": ("Move Speed", "Movement Speed"),
    "crit": ("Critical Rate", "Critical Strike Chance", "Crit Chance", "Crit Rate"),
    "healShieldPower": ("Heal and Shield Power", "Heal & Shield Power"),
    "physicalPen": ("Armor Penetration", "Armor Pen"),
    "physicalPenFlat": ("Armor Penetration", "Armor Pen"),
    "magicPen": ("Magic Penetration", "Magic Pen"),
    "magicPenFlat": ("Magic Penetration", "Magic Pen"),
    "physicalVamp": ("Physical Vamp",),
    "omnivamp": ("Omnivamp", "Omni Vamp"),
    "lifesteal": ("Lifesteal", "Life Steal"),
}


def _prettify(token: str) -> str:
    if token in STAT_WORDS:
        return STAT_WORDS[token]
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", token)
    return spaced[:1].upper() + spaced[1:]


def _clean_passive(text: str) -> str:
    """Passive text with the stat-icon markers resolved.

    A marker stands where the game draws a little stat icon, so it is only
    words when the sentence does not already say the stat. "current Health
    [hp]" is one stat mentioned once, not twice.
    """
    # icon marker directly before a +/number (e.g. "[physicalVamp] +8%") -> drop
    text = re.sub(r"\[([a-zA-Z]+)\]\s+(?=[+\d])", "", text)

    def resolve(m: re.Match) -> str:
        key = m.group(1)
        word = _prettify(key)
        names = "|".join(re.escape(n) for n in {word, key, *SAME_AS.get(key, ())})
        before, after = text[:m.start()], text[m.end():]
        # "base AD [ad]", "35% [hp] Health", "Movement Speed [moveSpeed]": the
        # icon repeats the word beside it, so the word alone is the meaning.
        if (re.search(rf"(?:{names})[\s,.;:]*$", before, re.I)
                or re.match(rf"[\s,.;:]*(?:{names})\b", after, re.I)):
            return ""
        return word

    text = re.sub(r"\[([a-zA-Z]+)\]", resolve, text)
    text = re.sub(r"\s+([,;:])", r"\1", text)
    text = re.sub(r"\s+\.(?!\.)", ".", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def main() -> None:
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    rules_path = ROOT / "data" / "item_stat_rules.json"
    stat_rules = (json.loads(rules_path.read_text(encoding="utf-8")).get("items", {})
                  if rules_path.exists() else {})
    rows = raw if isinstance(raw, list) else list(raw.values())
    out = []
    for it in rows:
        row = {
            "slug": it["slug"],
            "name": it["name"],
            "cost": it.get("cost", 0),
            "icon": it.get("icon"),
            "category": it.get("category", ""),
            "categories": it.get("categories", []),
            "tags": it.get("tags", []),
            "stats": it.get("stats", {}),
            "scopedStats": it.get("scopedStats", {}),
            "statRules": stat_rules.get(it["slug"], {}),
            "passives": [_clean_passive(p) for p in (it.get("passives") or [])],
        }
        # Which patch an item arrived in, and which one took it off the Rift.
        # A removed item keeps its record so builds collected while it existed
        # can still name and draw it; every surface that RECOMMENDS an item
        # filters on removedIn.
        for key in ("addedIn", "removedIn", "removedWhy", "upgradesTo", "bootsTier"):
            if it.get(key) is not None:
                row[key] = it[key]
        out.append(row)
    out.sort(key=lambda x: (x["category"], -x["cost"], x["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} items ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
