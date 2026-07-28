"""Recover the conditions the formula extraction dropped.

Two things the extractor records the existence of and then loses the number for:

  DURATIONS  A steroid says "+67.5% attack speed" and the tooltip says "for 5
             seconds", but only 51 of 235 steroids carry that duration. The
             engine treats an undated buff as permanent, so an undated 10-second
             ultimate runs for the whole fight and the champion's damage reads
             high. 161 of the 184 undated ones DO state a duration in their
             tooltip.

  EVERY-N    Six champions have an everyNHit passive with neither an `n` field
             nor a number in the evidence, so the engine assumes three.

Why a model and not a regex: the duration has to be the one attached to THAT
stat. Hecarim's Q says "Charges his halberd for 0.75 seconds" -- a charge time,
not a buff duration -- and a regex grabbing the first number would give him a
0.75s move-speed buff and make his damage read low. Trading an inflation bug for
a deflation bug is not a fix.

Output is an overlay, so re-extraction cannot eat it and a human correction
pinned there outranks the model.

    python -m scripts.recover_conditions            # everything outstanding
    python -m scripts.recover_conditions --only Gwen,Aatrox
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ability_conditions.json"
MODEL = "gemini-3.6-flash"

SYSTEM = ("You are reading Wild Rift ability tooltips. Answer ONLY from the text given. "
          "If the text does not state something, say null rather than guessing. Wild Rift "
          "is not League of Legends PC; do not import knowledge from it.")


def _key() -> str:
    for var in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(var):
            return os.environ[var]
    env = ROOT / "web-next" / ".env.local"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(("GEMINI_API_KEY", "GOOGLE_API_KEY")):
                return line.split("=", 1)[1].strip()
    sys.exit("GEMINI_API_KEY is not set")


def _load(name: str):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def timed(s: dict) -> bool:
    if isinstance(s.get("durationS"), (int, float)):
        return True
    return bool(re.search(r"\d+(\.\d+)?\s*second", str(s.get("note") or ""), re.I))


def outstanding() -> tuple[dict, dict]:
    """Champions needing steroid durations, and those needing an every-N count."""
    formulas = _load("ability_formulas.json")
    raw = _load("champions_wr.json")
    raw = list(raw.values()) if isinstance(raw, dict) else raw
    tips = {c["name"]: {str(a["slot"]): " ".join((a.get("text") or "").split())
                        for a in (c.get("abilities") or [])} for c in raw}

    durations: dict[str, list] = {}
    every_n: dict[str, str] = {}
    for name, rec in formulas.items():
        if name.startswith("_"):
            continue
        for slot, ab in (rec.get("abilities") or {}).items():
            for i, s in enumerate(ab.get("steroids") or []):
                if timed(s):
                    continue
                tip = tips.get(name, {}).get(slot, "")
                if not tip:
                    continue
                durations.setdefault(name, []).append(
                    {"slot": slot, "index": i, "stat": s.get("stat"), "tooltip": tip[:600]})
        mech = next((m for m in rec.get("mechanics") or []
                     if m.get("kind") == "everyNHit"), None)
        if mech and not isinstance(mech.get("n"), (int, float)):
            ev = str(mech.get("evidence") or "").lower()
            words = ("second", "other", "two", "third", "three", "fourth", "four",
                     "fifth", "five", "sixth", "six")
            if not any(f"every {w}" in ev for w in words):
                passive = tips.get(name, {}).get("P", "")
                if passive:
                    every_n[name] = passive[:600]
    return durations, every_n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_key())
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM, response_mime_type="application/json",
        temperature=0, max_output_tokens=8000)

    store = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {
        "_source": f"{args.model}, reading the scraped tooltip text",
        "_note": ("Recovered conditions the extraction dropped. An overlay, so "
                  "re-extraction does not lose it; a human correction here outranks "
                  "the model. null means the tooltip genuinely does not say."),
        "durations": {},
        "everyN": {},
    }
    wanted = {n.strip() for n in args.only.split(",") if n.strip()}
    durations, every_n = outstanding()

    todo = [(n, v) for n, v in durations.items()
            if (not wanted or n in wanted) and n not in store["durations"]]
    print(f"steroid durations: {len(store['durations'])} stored, {len(todo)} champions to ask")
    for i, (name, entries) in enumerate(todo, 1):
        listing = "\n".join(
            f'{j}. ability slot {e["slot"]}, buff stat "{e["stat"]}"\n   tooltip: {e["tooltip"]}'
            for j, e in enumerate(entries))
        prompt = (f"Champion: {name}\n\nFor each numbered buff below, how many SECONDS does "
                  "that specific buff last, according to its tooltip?\n"
                  "Only the duration of THAT stat's buff. A cast time, charge time, slow "
                  "duration or zone lifetime is NOT the buff duration unless the buff plainly "
                  "lasts exactly as long. If the tooltip does not state the buff's duration, "
                  "return null for it.\n\n"
                  f"{listing}\n\n"
                  'Return JSON: {"durations": [{"index": 0, "seconds": 5.0 or null, '
                  '"quote": "the exact words you read it from, or null"}]}')
        try:
            r = client.models.generate_content(model=args.model, contents=prompt, config=config)
            got = json.loads(r.text)
        except Exception as exc:                                   # noqa: BLE001
            if "RESOURCE_EXHAUSTED" in str(exc) or "429" in str(exc):
                print(f"\nSTOPPED at {name}: provider quota reached; re-run to continue.")
                break
            print(f"  {name}: failed, {str(exc)[:110]}")
            continue

        answers = {}
        for a in got.get("durations") or []:
            idx = a.get("index")
            secs = a.get("seconds")
            if not isinstance(idx, int) or idx >= len(entries):
                continue
            e = entries[idx]
            if isinstance(secs, (int, float)) and 0 < secs <= 60:
                answers[f'{e["slot"]}:{e["index"]}'] = {
                    "stat": e["stat"], "seconds": float(secs),
                    "quote": str(a.get("quote") or "")[:120],
                }
        store["durations"][name] = answers
        OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False), encoding="utf-8")
        found = len(answers)
        print(f"  [{i}/{len(todo)}] {name}: {found}/{len(entries)} durations recovered",
              flush=True)
        time.sleep(0.6)

    todo_n = [(n, tip) for n, tip in every_n.items()
              if (not wanted or n in wanted) and n not in store["everyN"]]
    print(f"\nevery-N counts: {len(todo_n)} champions to ask")
    for name, tip in todo_n:
        prompt = (f"Champion: {name}\nPassive tooltip: {tip}\n\n"
                  "Every how many attacks (or hits) does this passive trigger? "
                  'Return JSON: {"n": 3 or null, "quote": "the words you read it from or null"}')
        try:
            r = client.models.generate_content(model=args.model, contents=prompt, config=config)
            got = json.loads(r.text)
        except Exception as exc:                                   # noqa: BLE001
            print(f"  {name}: failed, {str(exc)[:110]}")
            continue
        n = got.get("n")
        if isinstance(n, (int, float)) and 1 < n <= 10:
            store["everyN"][name] = {"n": int(n), "quote": str(got.get("quote") or "")[:120]}
            OUT.write_text(json.dumps(store, indent=1, ensure_ascii=False), encoding="utf-8")
            print(f"  {name}: every {int(n)} ({got.get('quote', '')[:60]})")
        else:
            print(f"  {name}: tooltip does not state it, left assumed")
        time.sleep(0.6)

    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
