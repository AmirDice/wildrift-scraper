"""Ask Gemini whether each champion fights at melee or at range, and whether
Poke is a real build for them.

WHY A MODEL AND NOT A RULE. The rule was "Marksman, Mage and Enchanter are
ranged", and it is wrong often enough to matter: Lillia, Gragas, Rumble and
Vladimir are melee Mages, Nilah is a melee Marksman, Thresh and Rakan are melee
Enchanters. The scrape carries no attack-range field, so there is nothing to
read it off, and a keyword scan over ability text does not help either -- almost
every melee champion has at least one ability that travels.

The distinction that matters is not "has a ranged ability". It is where the
champion has to stand to do their damage. Diana throws a crescent and Kassadin
throws an orb, and both still have to be on top of you to kill you; that is the
judgement the classifier is being asked for, and it is the kind of judgement a
model is genuinely better at than a regex.

Poke is asked separately rather than derived, because ranged does not imply
poke: Kai'Sa is ranged and has no poke pattern at all, and a champion who has to
commit their cooldowns to trade is not poking.

Output goes to data/range_classification.json for review. Nothing is applied
automatically -- run with --apply to merge the agreed answers into
data/combat_profiles.json, which is the file the advisor and the studio read.

Run:
    python -m scripts.classify_range                    # classify everyone
    python -m scripts.classify_range --only "Lillia,Diana"
    python -m scripts.classify_range --apply            # merge into combat_profiles
    python -m scripts.classify_range --disagreements    # only where it differs from today
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "range_classification.json"
PROFILES = ROOT / "data" / "combat_profiles.json"
PLAYSTYLES = ROOT / "web-next" / "src" / "data" / "playstyles.json"
MODEL = "gemini-3.6-flash"

SYSTEM = (
    "You are a Wild Rift expert. Wild Rift is NOT League of Legends PC: abilities, "
    "attack ranges, items and champion kits differ between the two games, and several "
    "champions were reworked for mobile. Answer only about Wild Rift. If you are not "
    "confident about a champion, say so in `confidence` rather than guessing."
)

SCHEMA = (
    '{"attackType":"melee"|"ranged",'
    '"attackTypeReason":"one sentence about the BASIC ATTACK only",'
    '"combatRange":"short"|"long",'
    '"combatRangeReason":"one sentence: where the champion actually spends the fight",'
    '"longRangeDamageShare":"most"|"some"|"little",'
    '"pokeEligible":true|false,'
    '"pokeReason":"one sentence",'
    '"confidence":"high"|"medium"|"low"}'
)


def _load_key() -> str:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    env = ROOT / "web-next" / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(("GEMINI_API_KEY", "GOOGLE_API_KEY")):
                return line.split("=", 1)[1].strip()
    sys.exit("GEMINI_API_KEY is not set")


def champions() -> list[dict]:
    raw = json.loads((ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))
    return list(raw.values()) if isinstance(raw, dict) else raw


def prompt_for(c: dict) -> str:
    kit = "\n".join(
        f"[{a['slot']}] {a['name']}: {' '.join((a.get('text') or '').split())[:300]}"
        for a in (c.get("abilities") or [])[:5])
    return (
        f"Champion: {c['name']} ({c.get('class', '?')}, {c.get('role', '?')})\n\n{kit}\n\n"
        "Answer two questions about this champion IN WILD RIFT.\n\n"

        "1. ATTACK TYPE: is this champion melee or ranged?\n"
        "   This is about the BASIC ATTACK and about where the champion must stand to "
        "deal their damage -- NOT about whether they own an ability that travels. "
        "Nearly every melee champion has at least one ability with reach, and that does "
        "not make them ranged.\n"
        "   Several champions genuinely have both. Diana throws a crescent, Kassadin "
        "throws an orb, and both still have to be on top of the target to kill them: "
        "those are MELEE. Classify by the main kit and by how the champion actually "
        "fights, not by the longest range in the kit.\n"
        "   The champion's listed CLASS is unreliable here and is given only as "
        "context. Melee champions are routinely classed as Mage.\n\n"

        "2. COMBAT RANGE: in actual gameplay, where does this champion spend the "
        "fight?\n"
        "   This is a DIFFERENT question from question 1 and the answer is often "
        "different. Several champions have a ranged basic attack but still have to be "
        "in the middle of the fight for their kit to do anything: their healing, their "
        "engage, or their damage only works up close. Judge by how the champion is "
        "actually played and which abilities carry their damage and their impact -- not "
        "by the basic attack, and not by the single longest-range spell in the kit.\n"
        "   Answer 'short' if the champion has to get close to do their job, 'long' if "
        "they can do it from a distance and stay there.\n"
        "   Also answer longRangeDamageShare: how much of this champion's damage and "
        "impact actually comes from abilities used at long range -- 'most', 'some' or "
        "'little'.\n\n"

        "3. POKE: is a Poke build a real, playable option for this champion?\n"
        "   Poke means repeatable, reasonably safe damage from range BEFORE committing "
        "to a fight, on a short enough cooldown to do it repeatedly.\n"
        "   Being ranged is NOT enough. A ranged champion whose damage requires "
        "committing their cooldowns, or who wins by sustained basic attacks, is not a "
        "poke champion. A melee champion is never a poke champion.\n"
        "   Say false when in doubt: offering a build a champion cannot execute is "
        "worse than omitting one.\n\n"

        f"Return ONLY JSON: {SCHEMA}"
    )


def current_state() -> dict[str, str]:
    """What the site believes today, so the report can show disagreements."""
    sys.path.insert(0, str(ROOT))
    from web.advisor import profiles
    return {name: profiles.range_profile(name) for name in profiles.CHAMPIONS}


def apply_to_profiles(store: dict, min_confidence: str = "medium") -> None:
    """Write the two axes to the two places that consume them.

    They are genuinely different questions and were conflated before, which is
    what produced the wrong answer on four champions:

      rangeProfile (melee|ranged) -- the BASIC ATTACK. Gates ranged-only items
        like Runaan's Hurricane. Lillia, Thresh, Rakan and Vladimir are ranged
        here, and marking them melee to suppress Poke also wrongly withheld an
        item they are technically allowed to buy.

      noPoke -- whether a Poke build is playable. Driven by the model's
        pokeEligible, not by the attack type, because those four are ranged and
        still fight at short range with almost none of their damage coming from
        long range. That is the thing Poke actually asks about.

    Only exceptions are written to rangeProfile: ranged is the default for the
    classes that matter, so writing it back would bury the real entries.
    """
    rank = {"high": 3, "medium": 2, "low": 1}
    floor = rank.get(min_confidence, 2)
    data = json.loads(PROFILES.read_text(encoding="utf-8"))
    champs = data["champions"]
    entries = store.get("champions", {})

    confident = {n: e for n, e in entries.items()
                 if rank.get(e.get("confidence", "low"), 1) >= floor}
    skipped = sorted(set(entries) - set(confident))

    # Only EXCEPTIONS belong in this file. Marksman/Mage/Enchanter default to
    # ranged and everyone else to melee, so writing "melee" for Garen states
    # what the default already says and buries the entries that matter. A first
    # pass wrote 50 such rows before this check existed.
    ranged_classes = {"Marksman", "Mage", "Enchanter"}
    sys.path.insert(0, str(ROOT))
    from web.advisor import profiles as _profiles

    def default_is_melee(name: str) -> bool:
        return (_profiles.CHAMPIONS.get(name) or {}).get("class", "") not in ranged_classes

    melee_added, melee_removed = [], []
    for name, entry in sorted(confident.items()):
        record = champs.get(name) or {}
        # Hybrid is a human judgement the classifier cannot make: it only ever
        # answers melee or ranged, so letting it write here would flatten Gnar
        # and Jayce back to one mode and hand them ranged-only items.
        if record.get("rangeProfile") == "hybrid":
            continue
        if entry.get("attackType") == "melee":
            if default_is_melee(name):
                continue                      # the default already says this
            if record.get("rangeProfile") != "melee":
                champs.setdefault(name, {})["rangeProfile"] = "melee"
                champs[name].setdefault(
                    "reason", str(entry.get("attackTypeReason", ""))[:200])
                melee_added.append(name)
        elif record.get("rangeProfile") == "melee":
            # Classified ranged but currently overridden to melee. Drop the
            # override so item filtering is right; Poke is handled separately.
            record.pop("rangeProfile", None)
            record.pop("reason", None)
            if not record:
                champs.pop(name, None)
            melee_removed.append(name)

    data["champions"] = dict(sorted(champs.items()))
    PROFILES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    melee = sorted(n for n, v in data["champions"].items() if v.get("rangeProfile") == "melee")

    # noPoke is the union of three things, not just the model's verdict:
    #   - champions it confidently says cannot poke,
    #   - every champion the advisor already rejects for being melee, and
    #   - every champion it was NOT confident about.
    #
    # The second half: without it a low-confidence entry is skipped while the
    # advisor still refuses the playstyle, so the studio offers a Poke build the
    # generator then declines to produce. Rumble hit exactly that.
    #
    # The third half is the owner's call, and it is the right way round. Poke is
    # a build we advertise; offering one to a champion who cannot execute it
    # costs a player a game, while withholding one from a champion who could
    # costs them a menu entry. When the classifier is unsure, it does not get to
    # advertise.
    no_poke = {n for n, e in confident.items() if not e.get("pokeEligible")}
    no_poke |= {n for n in _profiles.CHAMPIONS
                if _profiles.range_profile(n) == "melee"
                or n in melee or default_is_melee(n)}
    no_poke |= set(entries) - set(confident)

    # An owner confirmation outranks every rule above it, including the melee
    # gate. Rell is the case that forced this: she is a melee Tank, so she was
    # excluded twice over -- once by the attack type and once by a Tank class
    # list that has no Poke entry to begin with -- and the owner still wants
    # Poke available for her. `userConfirmed` in range_classification.json is
    # the record of that decision, so a re-run of the classifier cannot quietly
    # revert it.
    poke_confirmed = sorted(
        n for n, e in entries.items()
        if e.get("userConfirmed") and e.get("pokeEligible") and n in _profiles.CHAMPIONS)
    no_poke -= set(poke_confirmed)
    no_poke = sorted(no_poke & set(_profiles.CHAMPIONS))

    ps = json.loads(PLAYSTYLES.read_text(encoding="utf-8"))
    ps.pop("meleeInRangedClass", None)
    ps.pop("_meleeNote", None)
    ps["_noPokeNote"] = (
        "Champions for whom a Poke build is not offered, classified by "
        "scripts/classify_range.py. This is NOT the same as being melee: Lillia, "
        "Thresh, Rakan and Vladimir all have ranged basic attacks and still belong "
        "here, because they fight at short range and almost none of their damage "
        "comes from long range. Champions the classifier was not confident about are "
        "also listed: an unsure answer does not get to advertise a build the player "
        "may not be able to execute. Poke is filtered out for everyone on this list.")
    ps["_pokeConfirmedNote"] = (
        "Owner-confirmed Poke champions. Outranks the melee gate and the noPoke "
        "list. Rell is here despite being a melee Tank, which is also why she "
        "needs an entry in `overrides` below: the Tank class list has no Poke "
        "entry, so confirming her eligible is not on its own enough to put Poke "
        "in her menu.")
    ps["pokeConfirmed"] = poke_confirmed
    ps["noPoke"] = no_poke

    # A confirmed champion whose CLASS never offers Poke needs the style added
    # explicitly, or the confirmation has no visible effect.
    by_class = ps.get("byClass", {})
    for name in poke_confirmed:
        champ_class = (_profiles.CHAMPIONS.get(name) or {}).get("class", "")
        if "poke" in (by_class.get(champ_class) or []):
            continue
        current = ps["overrides"].get(name) or list(by_class.get(champ_class) or [])
        if "poke" not in current:
            ps["overrides"][name] = [*current, "poke"]
            print(f"added Poke to {name}'s playstyle override "
                  f"(class {champ_class!r} does not grant it)")

    PLAYSTYLES.write_text(json.dumps(ps, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"rangeProfile: +{len(melee_added)} melee "
          f"({', '.join(melee_added) or 'none'})")
    print(f"rangeProfile: -{len(melee_removed)} corrected to ranged "
          f"({', '.join(melee_removed) or 'none'})")
    print(f"combat_profiles.json now lists {len(melee)} melee champions")
    print(f"playstyles.json noPoke now lists {len(no_poke)} champions")
    if skipped:
        print(f"skipped for confidence below {min_confidence}: {', '.join(skipped)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma-separated champion names")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--apply", action="store_true",
                    help="merge stored answers into combat_profiles.json")
    ap.add_argument("--min-confidence", default="medium", choices=("high", "medium", "low"))
    ap.add_argument("--disagreements", action="store_true",
                    help="print only where the model differs from the site today")
    args = ap.parse_args()

    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {
        "_note": "Generated by scripts/classify_range.py. Review before --apply.",
        "_model": args.model,
        "champions": {},
    }
    done = store.setdefault("champions", {})

    if args.apply:
        apply_to_profiles(store, args.min_confidence)
        return

    if args.disagreements:
        now = current_state()
        rows = [(n, e, now.get(n)) for n, e in sorted(done.items())
                if now.get(n) and e.get("attackType") != now[n]]
        print(f"{len(rows)} disagreements out of {len(done)} classified\n")
        for name, entry, site in rows:
            print(f"  {name:<16} site={site:<7} model={entry['attackType']:<7} "
                  f"({entry.get('confidence')})")
            print(f"      {entry.get('attackTypeReason', '')}")
        return

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_load_key())
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM, response_mime_type="application/json")

    wanted = [n.strip() for n in args.only.split(",") if n.strip()]
    todo = [c for c in champions()
            if (not wanted or c["name"] in wanted) and (wanted or c["name"] not in done)]
    print(f"{len(done)} already stored, {len(todo)} to fetch")

    for i, c in enumerate(todo, 1):
        try:
            r = client.models.generate_content(
                model=args.model, contents=prompt_for(c), config=config)
            got = json.loads(r.text)
        except Exception as exc:                                   # noqa: BLE001
            text = str(exc)
            if "RESOURCE_EXHAUSTED" in text or "429" in text:
                print(f"\nSTOPPED at {c['name']}: provider quota reached. "
                      f"{len(done)} stored so far; re-run to continue.")
                break
            print(f"  {c['name']}: failed, {text[:120]}")
            continue

        attack = str(got.get("attackType", "")).strip().lower()
        if attack not in ("melee", "ranged"):
            print(f"  {c['name']}: unusable attackType {attack!r}, skipped")
            continue
        done[c["name"]] = {
            "attackType": attack,
            "attackTypeReason": str(got.get("attackTypeReason", ""))[:300],
            "combatRange": str(got.get("combatRange", "")).strip().lower(),
            "combatRangeReason": str(got.get("combatRangeReason", ""))[:300],
            "longRangeDamageShare": str(got.get("longRangeDamageShare", "")).strip().lower(),
            "pokeEligible": bool(got.get("pokeEligible")),
            "pokeReason": str(got.get("pokeReason", ""))[:300],
            "confidence": str(got.get("confidence", "")).strip().lower(),
            "class": c.get("class", ""),
        }
        OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False), encoding="utf-8")
        e = done[c["name"]]
        poke = "poke" if e["pokeEligible"] else "no-poke"
        print(f"  [{i}/{len(todo)}] {c['name']:<16} attack={attack:<7} "
              f"fights={e['combatRange']:<6} longRangeDmg={e['longRangeDamageShare']:<7} "
              f"{poke:<8} ({e['confidence']})", flush=True)
        time.sleep(1)

    print(f"\n{len(done)} champions stored in {OUT.relative_to(ROOT)}")
    print("Review it, then: python -m scripts.classify_range --disagreements")


if __name__ == "__main__":
    main()
