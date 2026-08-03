"""Generate per-champion ITEMIZATION IDENTITY cards with Gemini.

The advisor already carries a kit-derived build identity (ability ratios ->
buildPathViability). What it cannot know from ability text is the META truth:
which archetypes this champion actually itemizes in practice, which tempting
paths are traps, and what the accepted flex patterns are ("one bruiser item in
an otherwise full-damage build"). The occasional weird build is almost always
an identity violation that kit derivation cannot catch -- crit on a champion
nobody builds crit on, a second bruiser item where the meta caps it at one.

These cards capture that meta knowledge once, from the strongest Gemini model,
as STRUCTURED data keyed by the same display names as champion_builds.json
(including transform forms like "Kayn (Rhaast)"). They are then:
  1. injected into the advisor prompt as a compact identity block, and
  2. used as a deterministic post-generation lint (hard "never" violations
     reject the build),
and validated against scraped top-50 player builds by
scripts/validate_champion_identity.py once capture sessions land.

Run:
    python -m scripts.generate_champion_identity                 # full roster
    python -m scripts.generate_champion_identity --only "Viego,Kayn (Rhaast)"
    python -m scripts.generate_champion_identity --force         # regenerate
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

from web.advisor import env  # noqa: E402  (loads keys from web-next/.env.local)

OUT = ROOT / "data" / "champion_identity.json"
BUILDS = ROOT / "data" / "champion_builds.json"

# The whole card speaks this vocabulary so the lint layer can be mechanical.
STAT_TOKENS = [
    "ad", "ap", "attack_speed", "crit", "lethality", "armor_pen", "magic_pen",
    "on_hit", "ability_haste", "hp", "armor", "mr", "mana", "energy",
    "healing_power", "shield_power", "move_speed", "lifesteal", "omnivamp",
]
STATUSES = ["primary", "viable", "situational", "flex_one_item", "off_meta", "never"]

PROMPT = """\
You are an expert analyst of League of Legends: Wild Rift itemization at the
highest ranks (Challenger). Produce the ITEMIZATION IDENTITY of one champion:
{who}.

Use your full knowledge of this champion in League of Legends PC as background,
but answer for WILD RIFT: where Wild Rift practice differs from PC (different
item pool, faster tempo, different balance), describe Wild Rift and say so in
the relevant note.

Be exhaustive about ARCHETYPES: for every itemization archetype that players
of this champion's class might plausibly attempt (for a fighter: crit,
attack-speed on-hit, lethality burst, full bruiser, tank, AP...), give an
explicit status verdict -- including the tempting-but-wrong ones, because the
point of this card is to stop a build generator from drifting into them. Answer
questions like: does this champion build crit, and if so is it crit PLUS
attack speed or attack speed alone? Is one bruiser or defensive item standard
inside an otherwise full-damage build, and which items fill that slot? Do AP
ratios in the kit translate into a real AP build, or is AP a trap? Is a tank
or utility variant genuinely played or only a meme?

Statuses: "primary" (the standard identity), "viable" (a real alternative seen
at high rank), "situational" (correct only under specific conditions; say the
conditions), "flex_one_item" (not a full path: exactly one item from this
archetype is commonly splashed; name typical items in the note),
"off_meta" (playable but suboptimal, should not be recommended), "never"
(violates the champion's identity; a build containing this is WRONG).

Stat tokens: use ONLY these, they feed a mechanical validator:
{stats}

Return JSON exactly in this shape:
{{
  "identitySummary": "<=25 words: what this champion fundamentally is, itemization-wise",
  "archetypes": [
    {{"path": "short archetype name", "status": "one of {statuses}", "note": "<=25 words"}}
  ],
  "statPriorities": ["ordered stat tokens the standard build stacks, most important first"],
  "avoidStats": ["stat tokens that must NOT drive item choices for this champion"],
  "flexPatterns": ["<=18 words each: accepted deviations, e.g. exactly one bruiser item late"],
  "signatureItems": ["Wild Rift item names that define this champion's standard build"],
  "threatProfile": {{
    "threats": ["<=10 words each: what this champion does TO enemies (healing, resets, true damage, poke...)"],
    "counterplay": ["<=10 words each: itemization answers enemies should buy against them"]
  }},
  "confidence": "high | medium | low -- your certainty about current WILD RIFT practice"
}}
"""


def _client_and_types():
    from google import genai
    from google.genai import types

    api_key = env.api_key("GEMINI_API_KEY") or env.api_key("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit(env.missing_key_message("GEMINI_API_KEY"))
    return genai.Client(api_key=api_key), types


def _who(display_name: str) -> str:
    """'Kayn (Rhaast)' -> a description that pins the exact form."""
    if "(" in display_name:
        base, form = display_name.split("(", 1)
        form = form.rstrip(") ")
        return (f"{base.strip()}, specifically his/her/their {form} form -- "
                f"profile THIS form's itemization, not the other form's")
    return display_name


def ladder_evidence(name: str) -> str:
    """Observed item frequencies from this champion's scraped top-50 builds,
    as prompt text. Empty when no complete capture session exists. Used for
    regenerating cards the validator flagged: the model reconciles its meta
    knowledge with what the ladder measurably plays."""
    try:
        from scripts.export_captures import find_sessions, _builds_by_rank
    except ImportError:
        return ""
    session = find_sessions(45).get(name.split(" (")[0])
    if session is None:
        return ""
    freq: dict[str, int] = {}
    builds = _builds_by_rank(session)
    for b in builds.values():
        for it in b.get("items", []):
            if it.get("slug"):
                freq[it["slug"]] = freq.get(it["slug"], 0) + 1
    if not freq:
        return ""
    n = len(builds)
    top = sorted(freq.items(), key=lambda kv: -kv[1])[:12]
    lines = ", ".join(f"{slug} in {c}/{n}" for slug, c in top)
    return (f"\nOBSERVED LADDER EVIDENCE (items actually equipped by the top {n} "
            f"ranked players of this champion in Wild Rift, freshly scraped): {lines}.\n"
            "Your card MUST be consistent with this evidence: an archetype the "
            "ladder measurably plays cannot be marked never or off_meta, and "
            "stats carried by frequently equipped items cannot be avoidStats.\n")


def generate_one(client, types, model: str, name: str) -> dict:
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.15,
        # Thinking models spend output budget on reasoning BEFORE the JSON;
        # 2048 truncated mid-card ('Unterminated string' at ~1.7KB) and
        # burned six retries per champion on the same wall.
        max_output_tokens=16384,
    )
    prompt = PROMPT.format(who=_who(name), stats=", ".join(STAT_TOKENS),
                           statuses="|".join(STATUSES)) + ladder_evidence(name)
    last: Exception | None = None
    for attempt in range(6):
        try:
            r = client.models.generate_content(model=model, contents=prompt, config=config)
            card = json.loads(r.text)
            problems = lint_card(card)
            if problems:
                raise ValueError("schema problems: " + "; ".join(problems))
            return card
        except Exception as exc:  # noqa: BLE001
            last = exc
            text = str(exc)
            # 429 = quota, 503 = preview model over capacity: both recover on
            # their own timescale, not ours -- wait long instead of failing.
            throttled = any(t in text for t in ("RESOURCE_EXHAUSTED", "429", "503", "UNAVAILABLE"))
            wait = 25 * (attempt + 1) if throttled else 3 * (attempt + 1)
            if attempt < 5:
                time.sleep(min(90, wait))
    raise RuntimeError(f"{name}: gemini failed: {str(last)[:200]}")


def lint_card(card: dict) -> list[str]:
    """Schema discipline at generation time, so downstream code can trust it."""
    out: list[str] = []
    if not isinstance(card.get("identitySummary"), str) or not card["identitySummary"].strip():
        out.append("identitySummary missing")
    arche = card.get("archetypes")
    if not isinstance(arche, list) or not arche:
        out.append("archetypes missing")
    else:
        if not any(a.get("status") == "primary" for a in arche if isinstance(a, dict)):
            out.append("no primary archetype")
        for a in arche:
            if not isinstance(a, dict) or a.get("status") not in STATUSES:
                out.append(f"bad archetype entry: {a!r}"[:80])
    for key in ("statPriorities", "avoidStats"):
        vals = card.get(key)
        if not isinstance(vals, list):
            out.append(f"{key} missing")
            continue
        bad = [v for v in vals if v not in STAT_TOKENS]
        if bad:
            out.append(f"{key} has unknown tokens {bad}")
    both = set(card.get("statPriorities") or []) & set(card.get("avoidStats") or [])
    if both:
        out.append(f"stats both prioritised and avoided: {sorted(both)}")
    tp = card.get("threatProfile")
    if not isinstance(tp, dict) or not tp.get("threats"):
        out.append("threatProfile missing")
    if card.get("confidence") not in ("high", "medium", "low"):
        out.append("confidence missing")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="gemini-3.1-pro-preview",
                    help="Identity is a one-time batch: use the strongest model available to the key")
    ap.add_argument("--only", default="",
                    help="Comma-separated display names (as in champion_builds.json)")
    ap.add_argument("--force", action="store_true", help="Regenerate existing cards")
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    names = [k for k in json.loads(BUILDS.read_text(encoding="utf-8")) if not k.startswith("_")]
    if args.only:
        wanted = {w.strip() for w in args.only.split(",") if w.strip()}
        unknown = wanted - set(names)
        if unknown:
            raise SystemExit(f"not in champion_builds.json: {sorted(unknown)}")
        names = [n for n in names if n in wanted]

    store: dict = {"_meta": {"model": args.model, "statTokens": STAT_TOKENS,
                             "statuses": STATUSES}, "champions": {}}
    if OUT.exists():
        store = json.loads(OUT.read_text(encoding="utf-8"))
        store.setdefault("champions", {})
    if not args.force:
        names = [n for n in names if n not in store["champions"]]
    if not names:
        print("nothing to do (use --force to regenerate)")
        return 0

    client, types = _client_and_types()
    lock = threading.Lock()
    done = failed = 0

    def work(name: str):
        card = generate_one(client, types, args.model, name)
        card["_generated"] = time.strftime("%Y-%m-%d")
        card["_model"] = args.model
        return name, card

    print(f"generating {len(names)} identity card(s) with {args.model}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, n): n for n in names}
        for fut in as_completed(futures):
            name = futures[fut]
            try:
                name, card = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  FAILED {name}: {str(exc)[:160]}")
                continue
            with lock:
                store["champions"][name] = card
                OUT.write_text(json.dumps(store, ensure_ascii=False, indent=2,
                                          sort_keys=True), encoding="utf-8")
            done += 1
            prim = next((a["path"] for a in card["archetypes"] if a["status"] == "primary"), "?")
            print(f"  [{done}/{len(names)}] {name}: primary={prim} "
                  f"confidence={card.get('confidence')}")

    print(f"\ndone: {done} written, {failed} failed -> {OUT.relative_to(ROOT)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
