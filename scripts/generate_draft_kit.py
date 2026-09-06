"""Capability numbers for the draft ranker, one card per champion.

`kitOf` in web-next/src/lib/draft-score.ts derives eleven 0-1 capability values
from a class, five boolean mechanics and a crowd-control depth. That places most
of the roster and cannot separate an archetype: Galio, Alistar and Rell derive
to the SAME vector, all three being "a Tank that protects allies with three
lockdown abilities", and the ranking then falls through to ladder strength and
answers every draft calling for that archetype with whoever is strongest this
patch.

Hand-authoring 141 x 11 numbers is the obvious fix and the slow one. This asks
the model instead, from the champion's own ability text, and then LINTS the
answer against facts that are already derived and already tested -- the class,
the measured crowd-control depth, whether the kit protects anybody but itself.
A card that contradicts those is rejected and retried rather than trusted.

That check is the whole point. champion_identity.json is generated the same way
and 97 of 139 of those cards recommended items the ladder never builds, because
nothing mechanical was standing between the model and the file. Here the model
is asked for judgement on axes it cannot get factually wrong without tripping a
gate.

    python -m scripts.generate_draft_kit                 # every champion
    python -m scripts.generate_draft_kit --only Lulu,Braum
    python -m scripts.generate_draft_kit --compare       # against hand-authored

Existing entries are kept unless --force: the file is owner-editable and a
correction someone made by hand outranks a regeneration.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.advisor import env, profiles  # noqa: E402

OUT = ROOT / "data" / "champion_draft_kit.json"
ROSTER = ROOT / "web-next" / "src" / "data" / "roster.json"

#: The axes, with an anchor for each. Without anchors the numbers are not
#: comparable between champions, which is the only thing they are for.
AXES = {
    "frontline": "Can stand in front and absorb a fight. 1.0 = Ornn, Malphite. "
                 "0.6 = a bruiser like Camille. 0.0 = any ranged carry.",
    "peel": "Keeping a TEAMMATE alive: shields, heals, cleanses, knocking an "
            "attacker off them. 1.0 = Lulu, Janna. 0.35 = Leona, whose crowd "
            "control is for starting fights. 0.0 = Katarina. A shield on "
            "YOURSELF is not peel.",
    "engage": "Starting a fight on your terms. 1.0 = Leona, Alistar, Rell. "
              "0.1 = Lulu. 0.0 = Soraka.",
    "antiDive": "Making the enemy regret jumping your backline: peel, "
                "interrupts, immunity. 1.0 = Lulu, Alistar. 0.3 = Blitzcrank. "
                "0.0 = Kog'Maw.",
    "antiTank": "Cutting through stacked health: percent-health damage, true "
                "damage, shred. 1.0 = Vayne, Kog'Maw. 0.4 = Caitlyn. 0.0 = a "
                "burst assassin who cannot kill a tank at all.",
    "disruption": "Breaking up a committed fight: interrupts, displacement, "
                  "big area crowd control, immunity. 1.0 = Alistar, Rell. "
                  "0.2 = Lulu.",
    "disengage": "Calling a fight OFF after it starts: knockbacks, speed, "
                 "untargetability. 1.0 = Janna's Monsoon. 0.05 = Leona, who "
                 "cannot take an engage back.",
    "sustained": "Damage over a whole fight rather than one rotation. "
                 "1.0 = Vayne, Kog'Maw, Master Yi. 0.2 = Veigar.",
    "magic": "Share of this champion's damage that is magic. 1.0 = pure AP, "
             "0.5 = genuinely mixed, 0.0 = pure physical.",
    "physical": "Share that is physical. The mirror of magic; the two should "
                "roughly sum to 1.",
    "globalPressure": "A map-wide ultimate that makes a split push safe. "
                      "1.0 = Twisted Fate, Galio, Shen. 0.0 = everyone else.",
}

PROMPT = """You are rating a League of Legends: Wild Rift champion for a DRAFT
assistant. Answer only from the kit below. Do not consider how popular or how
strong the champion currently is -- that is measured separately and mixed in
later. You are describing what the champion CAN DO.

CHAMPION: {name}
CLASS: {cls}
ABILITIES:
{abilities}

MEASURED FACTS about this champion, already verified. Your numbers must be
consistent with them:
- hard crowd-control abilities: {cc_depth}
- protects allies (a shield or heal that lands on someone else): {protects}
- has a dash or comparable movement: {dash}
- primary damage: {damage}
- draft tags: {tags}

Rate each axis from 0.0 to 1.0, using the anchors given:

{axes}

Return ONLY a JSON object mapping each axis name to a number. No prose.
"""


def _client_and_types():
    from google import genai
    from google.genai import types

    api_key = env.api_key("GEMINI_API_KEY") or env.api_key("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(env.missing_key_message("GEMINI_API_KEY"))
    return genai.Client(api_key=api_key), types


def abilities_of(name: str) -> str:
    record = profiles.CHAMPIONS.get(name) or {}
    out = []
    for a in record.get("abilities") or []:
        text = (a.get("text") or "").replace("\n", " ").strip()
        out.append("- %s: %s" % (a.get("name") or "?", text[:420]))
    return "\n".join(out) or "(no ability text available)"


def lint(name: str, card: dict, row: dict) -> list[str]:
    """Reject what contradicts a fact we already derived and tested.

    Judgement is the model's job; these are the places where judgement would
    have to be factually wrong, and each one maps to a trait with its own
    labelled test.
    """
    problems = []
    for axis in AXES:
        if axis not in card:
            problems.append("missing %s" % axis)
            continue
        v = card[axis]
        if not isinstance(v, (int, float)) or not (0 <= v <= 1):
            problems.append("%s=%r out of range" % (axis, v))
    if problems:
        return problems

    cls = row.get("class") or ""
    mech = row.get("mechanics") or []
    depth = row.get("ccDepth") or 0
    tags = row.get("archetypes") or []

    if cls not in ("Tank", "Bruiser", "Fighter") and card["frontline"] > 0.5:
        problems.append("frontline %.2f but class is %s" % (card["frontline"], cls))
    if depth == 0 and card["disruption"] > 0.5:
        problems.append("disruption %.2f but no hard crowd control" % card["disruption"])
    if not row.get("protectsAllies") and cls not in ("Tank", "Enchanter") \
            and card["peel"] > 0.6:
        problems.append("peel %.2f but nothing in the kit protects an ally"
                        % card["peel"])
    if "globalPressure" not in tags and card["globalPressure"] > 0.4:
        problems.append("globalPressure %.2f but no global ultimate"
                        % card["globalPressure"])
    if row.get("primaryDamage") == "physical" and card["magic"] > 0.6:
        problems.append("magic %.2f but damage is physical" % card["magic"])
    if row.get("primaryDamage") == "magic" and card["physical"] > 0.6:
        problems.append("physical %.2f but damage is magic" % card["physical"])
    if "dash" not in mech and card["disengage"] > 0.8 and not row.get("protectsAllies"):
        problems.append("disengage %.2f with no movement and no ally protection"
                        % card["disengage"])
    return problems


def generate_one(client, types, model: str, name: str, row: dict) -> dict:
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
        max_output_tokens=4096,
    )
    prompt = PROMPT.format(
        name=name,
        cls=row.get("class") or "?",
        abilities=abilities_of(name),
        cc_depth=row.get("ccDepth", 0),
        protects="yes" if row.get("protectsAllies") else "no",
        dash="yes" if "dash" in (row.get("mechanics") or []) else "no",
        damage=row.get("primaryDamage") or "?",
        tags=", ".join(row.get("archetypes") or []) or "none",
        axes="\n".join("%s: %s" % (k, v) for k, v in AXES.items()),
    )
    last = None
    for attempt in range(5):
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=config)
            card = json.loads(r.text)
            problems = lint(name, card, row)
            if problems:
                raise ValueError("; ".join(problems))
            return {k: round(float(card[k]), 2) for k in AXES}
        except Exception as exc:  # noqa: BLE001
            last = exc
            text = str(exc)
            throttled = any(t in text for t in ("RESOURCE_EXHAUSTED", "429", "503", "UNAVAILABLE"))
            if attempt < 4:
                time.sleep(min(60, (20 if throttled else 3) * (attempt + 1)))
    raise RuntimeError("%s: %s" % (name, str(last)[:200]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="gemini-3.6-flash")
    ap.add_argument("--only", default="", help="comma-separated champion names")
    ap.add_argument("--force", action="store_true",
                    help="regenerate entries that already exist")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--compare", action="store_true",
                    help="report agreement with the existing file and stop")
    args = ap.parse_args()

    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    existing = {}
    if OUT.exists():
        existing = (json.loads(OUT.read_text(encoding="utf-8")) or {}).get("champions", {})

    names = [n.strip() for n in args.only.split(",") if n.strip()] or sorted(roster)
    missing = [n for n in names if n not in roster]
    if missing:
        print("not in roster, skipped:", ", ".join(missing))
        names = [n for n in names if n in roster]

    if args.compare:
        return compare(existing)

    todo = names if args.force else [n for n in names if n not in existing]
    print("generating %d of %d (%d already present)"
          % (len(todo), len(names), len(names) - len(todo)))
    if not todo:
        return 0

    client, types = _client_and_types()
    lock = threading.Lock()
    done, failed = dict(existing), []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(generate_one, client, types, args.model, n, roster[n]): n
                   for n in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            name = futures[fut]
            try:
                card = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed.append(name)
                print("  [%3d/%d] FAILED %s: %s" % (i, len(todo), name, str(exc)[:110]))
                continue
            with lock:
                done[name] = card
            print("  [%3d/%d] %s" % (i, len(todo), name))

    doc = {
        "_comment": __doc__.strip().split("\n"),
        "schemaVersion": 1,
        "_model": args.model,
        "champions": dict(sorted(done.items())),
    }
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote %s: %d champions%s"
          % (OUT.name, len(done), (", %d failed" % len(failed)) if failed else ""))
    return 1 if failed else 0


def compare(cards: dict) -> int:
    """How far the model lands from values a person authored.

    Run before trusting a regeneration: these numbers decide draft advice, and
    an average that looks fine can hide an axis the model reads backwards.
    """
    hand = json.loads((ROOT / "data" / "champion_draft_kit.hand.json")
                      .read_text(encoding="utf-8"))["champions"]
    per_axis: dict[str, list[float]] = {}
    worst: list[tuple[float, str, str, float, float]] = []
    for name, ref in hand.items():
        got = cards.get(name)
        if not got:
            continue
        for axis, a in ref.items():
            b = got.get(axis)
            if b is None:
                continue
            per_axis.setdefault(axis, []).append(abs(a - b))
            worst.append((abs(a - b), name, axis, a, b))
    print("axis            mean gap   max")
    for axis, gaps in sorted(per_axis.items()):
        print("%-15s %.3f     %.2f" % (axis, sum(gaps) / len(gaps), max(gaps)))
    worst.sort(reverse=True)
    print("\nbiggest disagreements (hand -> model):")
    for gap, name, axis, a, b in worst[:15]:
        print("  %-12s %-14s %.2f -> %.2f   (%.2f)" % (name, axis, a, b, gap))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
