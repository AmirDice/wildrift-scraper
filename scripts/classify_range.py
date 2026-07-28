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
    '"attackTypeReason":"one sentence: where this champion has to stand to deal damage",'
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

        "2. POKE: is a Poke build a real, playable option for this champion?\n"
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
    """Merge agreed melee answers into combat_profiles.json.

    Only melee is written. Ranged is the default for the classes that matter, so
    writing it back would fill the overrides file with entries that change
    nothing and bury the real exceptions.
    """
    rank = {"high": 3, "medium": 2, "low": 1}
    floor = rank.get(min_confidence, 2)
    data = json.loads(PROFILES.read_text(encoding="utf-8"))
    champs = data["champions"]

    added, skipped = [], []
    for name, entry in sorted(store.get("champions", {}).items()):
        if entry.get("attackType") != "melee":
            continue
        if rank.get(entry.get("confidence", "low"), 1) < floor:
            skipped.append(f"{name} ({entry.get('confidence')})")
            continue
        record = champs.setdefault(name, {})
        if record.get("rangeProfile") == "melee":
            continue
        record["rangeProfile"] = "melee"
        record.setdefault("reason", str(entry.get("attackTypeReason", ""))[:200])
        added.append(name)

    data["champions"] = dict(sorted(champs.items()))
    PROFILES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    melee = sorted(n for n, v in data["champions"].items() if v.get("rangeProfile") == "melee")
    ps = json.loads(PLAYSTYLES.read_text(encoding="utf-8"))
    ps["meleeInRangedClass"] = melee
    PLAYSTYLES.write_text(json.dumps(ps, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"added {len(added)} melee overrides: {', '.join(added) or '(none)'}")
    if skipped:
        print(f"skipped for low confidence: {', '.join(skipped)}")
    print(f"combat_profiles.json and playstyles.json now list {len(melee)} melee champions")


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
            "pokeEligible": bool(got.get("pokeEligible")),
            "pokeReason": str(got.get("pokeReason", ""))[:300],
            "confidence": str(got.get("confidence", "")).strip().lower(),
            "class": c.get("class", ""),
        }
        OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False), encoding="utf-8")
        poke = "poke" if done[c["name"]]["pokeEligible"] else "no-poke"
        print(f"  [{i}/{len(todo)}] {c['name']:<16} {attack:<7} {poke:<8} "
              f"({done[c['name']]['confidence']})", flush=True)
        time.sleep(1)

    print(f"\n{len(done)} champions stored in {OUT.relative_to(ROOT)}")
    print("Review it, then: python -m scripts.classify_range --disagreements")


if __name__ == "__main__":
    main()
