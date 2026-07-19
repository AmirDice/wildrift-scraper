"""Apply patch 7.2a balance changes on top of the 7.2 item scrape.

wr-meta is 7.2, not 7.2a: it still shows Blade of the Ruined King's melee
on-hit at 10%, which 7.2a nerfs to 8.5%. So these deltas are transcribed from
the official notes and applied over the scrape.

    https://wildrift.leagueoflegends.com/en-gb/news/game-updates/wild-rift-patch-notes-7-2a/

Ranked only: ARAM / AAA / adventure-mode changes are deliberately excluded.

Every edit asserts the CURRENT value first. If the source data shifts under us
(a re-scrape, a 7.2b), the assert fails loudly instead of silently doing
nothing and leaving us to wonder why a nerf never landed.

Run:
    python -m scripts.apply_patch_7_2a           # dry run
    python -m scripts.apply_patch_7_2a --write
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# (slug, stat_key, old, new) -- numeric stat nerfs
STAT_CHANGES = [
    ("armorcrusher-boots", "physicalPenFlat", 12.0, 10.0),
    ("armorcrusher-boots", "ad", 25.0, 20.0),
]

# (slug, old_substring, new_substring) -- passive text, so the effect extractor
# reads the 7.2a numbers rather than the 7.2 ones.
TEXT_CHANGES = [
    # Ruined Strikes melee 10% -> 8.5% (the RANGED 7% is already 7.2-correct).
    # NB: matches the CLEANED text (scrape_wrmeta.clean_text strips the padded
    # parens), not the raw "(Melee attacks deal 10% )" the site serves.
    ("blade-of-the-ruined-king", "(Melee attacks deal 10%)", "(Melee attacks deal 8.5%)"),
    # Manamune: Mana Charge per stack 18 -> 14
    ("manamune", "Increases max Mana by 18", "Increases max Mana by 14"),
    # Muramana: Shock AD ratio 6% -> 4.5%
    ("muramana", "amount consumed + 6% [ad]", "amount consumed + 4.5% [ad]"),
    # Seraph's Embrace: Lifeline shield ratio 20% -> 16%
    ("seraphs-embrace", "consumes 20% of your current Mana", "consumes 16% of your current Mana"),
]

# Champion ability text. None of these 5 are in the 16-champion test set, so this
# changes no build today; it lands the 7.2a numbers in the source text so the
# full 141-champion extraction reads them instead of the 7.2 values.
# (champion, ability_name, old_substring, new_substring)
CHAMP_TEXT = [
    ("Nidalee", "Bushwhack / Pounce",
     "dealing 65 / 100 / 135 / 170", "dealing 55 / 90 / 125 / 160"),
    ("Nidalee", "Aspect Of The Cougar",
     "gains 2 ( +3% AP ) bonus Armor", "gains 2 ( +2.5% AP ) bonus Armor"),
    ("Warwick", "Eternal Hunger",
     "( +20% bonus AD +10% AP )", "( +15% bonus AD +10% AP )"),
    ("Warwick", "Jaws of the Beast",
     "( 120% AD + 90% AP )", "( 120% AD + 85% AP )"),
    # Riot groups this as "Shattered Earth/Upheaval 10% -> 11%", but the text
    # carries TWO values: the third attack's 10% and Upheaval's 9%. Only the
    # explicit 10% is changed; the 9% is left alone rather than guessed at.
    ("Skarner", "Shattered Earth",
     "an additional 10% of the target's max Health",
     "an additional 11% of the target's max Health"),
    ("Skarner", "Seismic Bastion",
     "absorbs damage equal to 8% max Health", "absorbs damage equal to 10% max Health"),
    ("Senna", "Absolution",
     "dealing 1.2% of their current health", "dealing 1% of their current health"),
    ("Senna", "Dawning Shadow",
     "( +40% AP + 4 per Mist)", "( +50% AP + 2.5 per Mist)"),
    # NB: the source text really does read "4 0" (typo), which makes this the
    # unique healing line -- the identical 20/30/40 further down is wave DAMAGE.
    ("Yuumi", "Final Chapter",
     "Restores 20 / 30 / 4 0 ( +5% AP ) Health",
     "Restores 20 / 35 / 50 ( +5% AP ) Health"),
]

# (champion, ability_name, old_cooldowns, new_cooldowns) -- a separate field
CHAMP_CDS = [
    ("Skarner", "Seismic Bastion", ["9", "8", "7", "6"], ["8", "7", "6", "5"]),
    ("Skarner", "Ixtal's Impact", ["20", "18", "16", "14"], ["18", "16", "14", "12"]),
]

# Changes we cannot represent: our champion data stores no mana costs.
UNAPPLIED = ["Yuumi / Zoomies: mana cost 80/90/100/110 -> 65/75/85/95 "
             "(we store no mana costs)"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    items = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    by = {i["slug"]: i for i in items}
    edits = 0

    skipped = 0
    for slug, key, old, new in STAT_CHANGES:
        it = by.get(slug)
        if not it:
            raise SystemExit(f"7.2a: {slug} not in items.json")
        cur = (it.get("stats") or {}).get(key)
        if cur is None:
            raise SystemExit(f"7.2a: {slug} has no stat {key} (has {list(it['stats'])})")
        if cur["value"] == new:
            skipped += 1          # already 7.2a; re-running must not be an error
            continue
        if cur["value"] != old:
            raise SystemExit(f"7.2a: {slug}.{key} expected {old} (or {new}), "
                             f"found {cur['value']}")
        cur["value"] = new
        edits += 1
        print(f"  stat  {slug:26} {key:16} {old} -> {new}")

    for slug, old, new in TEXT_CHANGES:
        it = by.get(slug)
        if not it:
            raise SystemExit(f"7.2a: {slug} not in items.json")
        hit = [i for i, p in enumerate(it["passives"]) if old in p]
        if not hit:
            if any(new in p for p in it["passives"]):
                skipped += 1      # already applied
                continue
            raise SystemExit(f"7.2a: {slug} passive text not found: {old!r}\n"
                             f"      have: {it['passives']}")
        for i in hit:
            it["passives"][i] = it["passives"][i].replace(old, new)
        edits += 1
        print(f"  text  {slug:26} {old!r} -> {new!r}")

    print(f"\n{edits} item edits applied\n")

    # ---- champions
    champs = json.loads((DATA / "champions_wr.json").read_text(encoding="utf-8"))
    listed = list(champs.values()) if isinstance(champs, dict) else champs
    by_name = {c.get("name"): c for c in listed}

    def _ability(champ: str, ability: str) -> dict:
        c = by_name.get(champ)
        if not c:
            raise SystemExit(f"7.2a: champion {champ} not found")
        for a in c.get("abilities") or []:
            if (a.get("name") or "").lower() == ability.lower():
                return a
        raise SystemExit(f"7.2a: {champ} has no ability {ability!r} "
                         f"(has {[a.get('name') for a in c.get('abilities') or []]})")

    cedits = 0
    for champ, ability, old, new in CHAMP_TEXT:
        a = _ability(champ, ability)
        txt = a.get("text") or ""
        if old not in txt:
            if new in txt:
                skipped += 1      # already 7.2a; re-running must not be an error
                continue
            raise SystemExit(f"7.2a: {champ}/{ability} text missing {old!r}\n"
                             f"      have: {txt}")
        a["text"] = txt.replace(old, new)
        cedits += 1
        print(f"  text  {champ:8} {ability:22} {old!r} -> {new!r}")

    for champ, ability, old, new in CHAMP_CDS:
        a = _ability(champ, ability)
        cur = list(a.get("cooldowns") or [])
        if cur == new:
            skipped += 1          # already applied
            continue
        if cur != old:
            raise SystemExit(f"7.2a: {champ}/{ability} cooldowns expected {old} "
                             f"(or {new}), found {cur}")
        a["cooldowns"] = new
        cedits += 1
        print(f"  cds   {champ:8} {ability:22} {old} -> {new}")

    print(f"\n{cedits} champion edits applied | {skipped} already at 7.2a (skipped)")
    for u in UNAPPLIED:
        print(f"  NOT APPLIED: {u}")

    if args.write:
        (DATA / "items.json").write_text(json.dumps(items, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
        (DATA / "champions_wr.json").write_text(
            json.dumps(champs, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\nwrote data/items.json + data/champions_wr.json")
    else:
        print("\n(dry run: pass --write to apply)")


if __name__ == "__main__":
    main()
