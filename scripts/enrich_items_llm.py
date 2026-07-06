"""Offline LLM enrichment for the build optimizer (Gemini).

The deterministic scorer in web/build_optimizer.py can read an item's *stats*
but not judge the *value of its passive* for a given champion archetype — a
linear stat sum can't see that Infinity Edge's crit-amp passive is huge for a
crit ADC, or that Ardent Censer's aura is core for an enchanter.

This script asks Gemini to make that judgement ONCE per patch and caches it to
data/items_enriched.json. The scorer then adds a `passiveValue[archetype]` term
and force-includes `coreFor` items. The LLM only *judges real scraped passives*
— it never invents items or stats — and the output is committed & reviewable, so
the whole system stays deterministic and reproducible at build/serve time.

Run (needs GEMINI_API_KEY or GOOGLE_API_KEY):
    python -m scripts.enrich_items_llm            # enrich all items (resumable)
    python -m scripts.enrich_items_llm --limit 12 # quick test on 12 items
    python -m scripts.enrich_items_llm --fresh    # ignore cache, redo all
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from web.build_optimizer import ARCHETYPES

ROOT = Path(__file__).resolve().parent.parent
ITEMS = ROOT / "data" / "items.json"
OUT = ROOT / "data" / "items_enriched.json"

MODEL = "gemini-2.5-flash"  # fast + cheap; use gemini-2.5-pro for max quality
BATCH = 12  # items per API call

ARCHETYPE_DESC = {
    "crit-adc": "Crit marksman (Jinx, Ashe) — stacks crit chance/damage + attack speed + lifesteal.",
    "bruiser": "Bruiser/fighter (Hecarim, Aatrox) — AD + health + ability haste + sustain, some on-hit.",
    "assassin": "Assassin (Zed, Talon) — AD + lethality/armor pen + ability haste for burst.",
    "burst-mage": "Burst mage (Lux, Annie) — AP + magic penetration + ability haste.",
    "tank": "Tank (Amumu, Malphite) — health + armor + magic resist + ability haste, defensive auras.",
    "enchanter": "Enchanter support (Lulu, Nami) — heal/shield power + ability haste + mana, team auras.",
}

SYSTEM = (
    "You are a Wild Rift itemization expert. You judge how valuable each item's "
    "PASSIVE (not its raw stats — those are scored separately) is to each build "
    "archetype. Be decisive and grounded in the passive text you are given. "
    "Never invent items or effects."
)

ARCHETYPE_KEYS = list(ARCHETYPES.keys())


def _prompt(items: list[dict]) -> str:
    arche_lines = "\n".join(f"- {k}: {ARCHETYPE_DESC[k]}" for k in ARCHETYPE_KEYS)
    item_lines = []
    for it in items:
        stats = ", ".join(f"{k} {v['value']}{'%' if v['percent'] else ''}"
                          for k, v in it["stats"].items()) or "none"
        passives = " ".join(it["passives"]) or "(no passive)"
        item_lines.append(
            f'- slug="{it["slug"]}" name="{it["name"]}" category={it["category"]} '
            f'cost={it["cost"]}\n  stats: {stats}\n  passive: {passives}'
        )
    items_block = "\n".join(item_lines)
    return f"""Archetypes:
{arche_lines}

For EACH item below, judge its PASSIVE's value to each archetype and return JSON.

Rules:
- passiveValue: a number 0.0-1.0 per archetype (0 = passive useless/irrelevant to
  that archetype, 1 = passive is build-defining for it). Only rate the PASSIVE's
  contribution, not the raw stats. Items with no passive get all zeros.
- coreFor: list of archetype keys this item is a near-mandatory core buy for
  (e.g. Infinity Edge -> ["crit-adc"]). Usually empty or one entry. Be strict.
- note: one short clause explaining the passive's main value (<=12 words).

Return ONLY a JSON array, one object per item, no prose:
[{{"slug": "...", "passiveValue": {{"crit-adc": 0.0, "bruiser": 0.0, "assassin": 0.0, "burst-mage": 0.0, "tank": 0.0, "enchanter": 0.0}}, "coreFor": [], "note": "..."}}]

Items:
{items_block}
"""


def _extract_json(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        raise ValueError("no JSON array in model output")
    return json.loads(m.group(0))


def _clean(entry: dict) -> dict:
    pv = entry.get("passiveValue", {}) or {}
    pv = {k: round(float(pv.get(k, 0) or 0), 3) for k in ARCHETYPE_KEYS}
    core = [c for c in (entry.get("coreFor") or []) if c in ARCHETYPE_KEYS]
    return {"passiveValue": pv, "coreFor": core, "note": str(entry.get("note", "")).strip()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    items = json.loads(ITEMS.read_text(encoding="utf-8"))
    if args.limit:
        items = items[: args.limit]

    cache: dict[str, dict] = {}
    if OUT.exists() and not args.fresh:
        cache = json.loads(OUT.read_text(encoding="utf-8"))

    todo = [it for it in items if it["slug"] not in cache]
    print(f"{len(items)} items | {len(cache)} cached | {len(todo)} to enrich")
    if not todo:
        print("nothing to do")
        return

    # Client reads GEMINI_API_KEY (or GOOGLE_API_KEY) from the environment.
    client = genai.Client()
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM,
        response_mime_type="application/json",
        temperature=0.2,
    )
    by_slug = {it["slug"]: it for it in items}

    for i in range(0, len(todo), BATCH):
        batch = todo[i : i + BATCH]
        # retry transient API errors (503 overloaded / 429 rate limit / 5xx)
        text = ""
        for attempt in range(5):
            try:
                resp = client.models.generate_content(
                    model=args.model, contents=_prompt(batch), config=config,
                )
                text = resp.text or ""
                break
            except (genai_errors.ServerError, genai_errors.ClientError) as e:
                code = getattr(e, "code", None)
                if code in (429, 500, 502, 503, 504) and attempt < 4:
                    wait = 3 * (attempt + 1)
                    print(f"  … batch {i//BATCH+1} got {code}, retry in {wait}s")
                    time.sleep(wait)
                    continue
                raise
        try:
            rows = _extract_json(text)
        except Exception as e:  # noqa: BLE001
            print(f"  ! batch {i//BATCH+1} parse failed: {e} — skipping, rerun to retry")
            continue
        for row in rows:
            slug = row.get("slug")
            if slug in by_slug:
                cache[slug] = _clean(row)
        OUT.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        done = sum(1 for it in items if it["slug"] in cache)
        print(f"  batch {i//BATCH+1}: +{len(rows)}  ({done}/{len(items)} total)")

    # quick sanity: show what got flagged core
    core = {c: [s for s, v in cache.items() if c in v["coreFor"]] for c in ARCHETYPE_KEYS}
    print("\ncoreFor:")
    for k, v in core.items():
        print(f"  {k}: {v}")
    print(f"\nwrote {OUT.relative_to(ROOT)} ({len(cache)} items)")


if __name__ == "__main__":
    main()
