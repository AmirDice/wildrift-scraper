"""One grounded paragraph per champion: what its numbers actually say.

WHY THIS IS NOT "explain the tier". The tier is a band cut from a number the
pipeline computed, so "why is it S" answers itself -- "because 52.3 falls
between 52 and 53.5" -- and a model asked that question fills the vacuum with
game knowledge it was never given. That is the one failure mode this codebase
is built to refuse (see extract_formulas' verbatim grounding, and the
stub-scrape test in tests/test_profiles.py). So the model is asked a question
it CAN answer from the data: what is unusual, or not, about this champion's
profile.

GROUNDING. The model sees one champion's facts and nothing else. Every number
it writes must appear in that fact sheet, checked mechanically after
generation; a sentence carrying an unsourced number rejects the whole
generation and retries. It is also told, explicitly, that "nothing stands out"
is a correct answer -- a model made to find a story for all 141 champions will
invent 100 of them.

Output: web-next/src/data/tier_explanations.json
    {"generatedAt": ..., "model": ..., "champions": {"<slug>": {"text": ...}}}

Run (needs GEMINI_API_KEY, read from web-next/.env.local like everything else):
    python -m scripts.generate_tier_explanations --only "Hecarim,Yuumi,Garen"
    python -m scripts.generate_tier_explanations --limit 10
    python -m scripts.generate_tier_explanations              # whole roster
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
WEB_DATA = ROOT / "web-next" / "src" / "data"
OUT = WEB_DATA / "tier_explanations.json"

MODEL = os.environ.get("EXPLAIN_MODEL", "gemini-3.6-flash")

SYSTEM = """You write one short paragraph about a Wild Rift champion for a stats site.

You are given that champion's measured numbers and nothing else. Write only what
those numbers support.

HARD RULES
- Every number you write must appear in the facts given to you. Never compute,
  estimate, round differently, or infer a number that is not there.
- Never explain the champion's KIT, abilities, combos or playstyle. You were not
  given them and you do not know them.
- Never give advice, predictions, or "expect this to change".
- "Nothing unusual" is a correct and expected answer. Most champions are ordinary.
  If the profile is unremarkable, say so plainly in one short sentence and stop.
- Never write a sentence that would be equally true of a different champion. If a
  claim could be pasted onto any champion, delete it.

WHAT IS WORTH SAYING, when the numbers show it
- A win rate far from the middle, and how deep the sample behind it is.
- A one-trick-heavy board (high OTP score): the win rate reflects specialists
  rather than typical players.
- Consistency: a low spread means most of the top players get the same result; a
  high spread means results depend heavily on the player.
- Time since the last balance change: a long-unchanged champion whose win rate is
  extreme was solved, not buffed. A recent change is worth naming with its patch.
- Movement since the previous collection, including tier crossings.
- Agreement or disagreement between servers.

WRITE FOR A PLAYER, NOT A DASHBOARD
- Never name the internal metrics. "One-trick concentration score of 78.6 out of
  100" means nothing to a reader; "most of that win rate comes from a handful of
  specialists" is the same fact in their language. The interpretation is given to
  you beside each number: write the interpretation, and use the number only where
  it adds weight.
- Do not list every fact you were given. Pick the two or three that make this
  champion different and ignore the rest.
- Lead with the thing a player would find surprising, not with the win rate they
  can already see on the page.
- Do not use a stock opening formula. "Regional performance varies" and similar
  scene-setting phrases carry no information: open on the specific fact itself.
- Vary the sentence shape. Do not lean on "Despite ..." as an opener; it fits at
  most one champion in ten and reads as a tic when every entry uses it.

STYLE
- 2 to 4 sentences. Plain, factual, no hype. No em-dashes. No emoji.
- Do not restate the champion's name more than once.
- Do not open with "This champion" or the tier letter."""


def _facts(champ: dict, na: dict | None, cn: dict | None,
           history: list[dict], patch_days: int | None) -> tuple[str, set[str]]:
    """The fact sheet the model may draw on, and the set of number-strings that
    are therefore legal in its answer."""
    lines: list[str] = []
    allowed: set[str] = set()

    def fact(label: str, value, *, numbers: list = ()) -> None:
        lines.append(f"{label}: {value}")
        for n in (numbers or []):
            if n is None:
                continue
            allowed.add(_numstr(n))

    fact("Champion", champ["name"])
    fact("Role", champ.get("role") or "unknown")
    fact("Class", champ.get("class") or "unknown")
    fact("Tier (EU)", champ.get("tier"))
    fact("EU win rate", f"{champ['wr']}%", numbers=[champ["wr"]])
    # meanWr is deliberately NOT offered. It is the raw mean of the top 50 while
    # `wr` is the weighted, shrunk version of the same pool (both centred by the
    # same offset in export_json), so the two differ by several points on some
    # champions -- Corki reads 48.8 and 52.0 -- and a model handed both wrote
    # sentences that look like they contradict the headline number.
    if champ.get("maxWr") is not None:
        # Kept RAW by export_json on purpose: it is one player's actual record,
        # not a centred champion average. Saying so stops the model presenting
        # the gap to the champion win rate as if the two were the same measure.
        fact("Best single player's own record (a real unadjusted win rate, not "
             "comparable to the centred champion averages above)",
             f"{champ['maxWr']}%", numbers=[champ["maxWr"]])
    if champ.get("nPlayers") is not None:
        fact("Players measured", champ["nPlayers"], numbers=[champ["nPlayers"]])
    if champ.get("medianGames") is not None:
        fact("Median games per player", champ["medianGames"], numbers=[champ["medianGames"]])
    if champ.get("totalGames") is not None:
        fact("Total games in the sample", champ["totalGames"], numbers=[champ["totalGames"]])

    # The next two are deliberately given WITHOUT their numbers. "78.6 out of
    # 100" and "8.03 points of excess spread" are internal scales that mean
    # nothing to a reader, and while the model could see them it recited them
    # verbatim instead of translating. Withholding the figure leaves it nothing
    # to parrot: the interpretation is the fact. Every number that survives
    # here is one a player can actually read (percentages, games, days).
    otp = champ.get("otpScore")
    if otp is not None:
        # Bands per web/data_loader.py: ~50 is typical, 85+ earns the badge.
        # Phrased so it cannot be read as "casual players". EVERY player in
        # this sample is in the champion's top 50; the axis is how concentrated
        # their games are, not how good they are. The model previously turned
        # "few one-tricks" into "casual users", which is false of all 50.
        band = ("a few dedicated one-tricks play most of the games, so this "
                "reflects specialists more than the rest of the top 50" if otp >= 75
                else "somewhat more concentrated on one-tricks than usual" if otp >= 60
                else "the top 50 spread their games evenly, with no small group of "
                     "one-tricks dominating the board" if otp <= 30
                else "a normal mix of one-tricks and broader players")
        fact("How concentrated the games are (all 50 are top-ranked players; "
             "this is about how the games are spread, not player skill)", band)

    spread = champ.get("winrateStd")
    if spread is not None:
        band = ("results vary a lot between individual players, so the champion is "
                "far more rewarding for some of the top 50 than others" if spread >= 8
                else "nearly all of the top players get a similar result, so the win "
                     "rate is reliable rather than carried by a few" if spread <= 4
                else "a normal amount of player-to-player variation")
        fact("How consistent it is across players", band)

    delta = champ.get("wrDelta")
    if delta is not None and abs(delta) >= 0.5:
        # Below half a point is sampling noise between two 50-player reads, and
        # handing it over produced "shifted by 0.0 points" as though it meant
        # something. Silence is the honest version.
        fact("Win rate change since the previous collection",
             f"{'+' if delta > 0 else ''}{delta} points", numbers=[delta, abs(delta)])
    elif delta is not None:
        fact("Win rate change since the previous collection",
             "essentially unchanged")
    if champ.get("tierMoved") and champ.get("prevTier"):
        fact("Tier movement", f"was {champ['prevTier']} tier, now {champ['tier']}")

    if patch_days is not None and history:
        last = history[-1]
        fact("Last balance change",
             f"patch {last.get('patch')}, {patch_days} days ago",
             numbers=[patch_days, last.get("patch")])
        summary = (last.get("summary") or "").strip()
        if summary:
            fact("What that patch did", summary[:180])
    elif not history:
        fact("Balance history", "this champion has never had a recorded balance change")

    if na and na.get("wr") is not None:
        fact("NA win rate", f"{na['wr']}% ({na.get('tier')} tier there)", numbers=[na["wr"]])
        gap = round(na["wr"] - champ["wr"], 1)
        fact("NA minus EU", f"{'+' if gap > 0 else ''}{gap} points", numbers=[gap, abs(gap)])
    else:
        fact("NA", "not collected yet")
    if cn and cn.get("wr") is not None:
        fact("China win rate", f"{cn['wr']}% (whole-population sample, not top 50)",
             numbers=[cn["wr"]])

    return "\n".join(lines), allowed


def _numstr(n) -> str:
    """Canonical string for a number, so 60.2, '60.2' and '48.0' vs 48 all
    compare equal. The string branch must normalise too: it did not, so a
    fact of 48.0 was stored as "48" while the model's correct "48.0%" read
    back as "48.0" and every Yuumi generation was rejected as unsourced."""
    if isinstance(n, str):
        try:
            f = float(n.strip())
        except ValueError:
            return n.strip()
    else:
        f = float(n)
    return str(int(f)) if f == int(f) else str(round(f, 2))


_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
# Small integers are ordinary prose ("two servers", "50%" as the midpoint) and
# a champion count of 50 is in every fact sheet; requiring them to be sourced
# rejects good paragraphs for no benefit.
_FREE_NUMBERS = {"0", "1", "2", "3", "4", "5", "50", "100"}


def _ungrounded(text: str, allowed: set[str]) -> list[str]:
    """Numbers the model wrote that were not in its facts.

    Thousands separators are stripped first: the model writes "3,499 games",
    which the digit regex would otherwise split into "3" and "499" and reject
    as unsourced. Nearly every champion has a four-digit game count, so this
    rejected almost the whole roster."""
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    bad = []
    for raw in _NUM_RE.findall(text):
        canon = _numstr(raw)
        if canon in _FREE_NUMBERS or canon in allowed:
            continue
        # "7.2b" style patch labels arrive with a letter suffix.
        if any(a.startswith(canon) for a in allowed):
            continue
        bad.append(raw)
    return bad


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).days


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", default="", help="comma-separated champion names")
    ap.add_argument("--limit", type=int, default=0, help="stop after N champions")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the fact sheet for each champion and make no API call")
    args = ap.parse_args()

    from src.scrape_timed import _ensure_gemini_key
    if not args.dry_run and not _ensure_gemini_key():
        raise SystemExit("GEMINI_API_KEY not found (env or web-next/.env.local)")

    site = json.loads((WEB_DATA / "site.json").read_text(encoding="utf-8"))
    na_site = json.loads((WEB_DATA / "site_na.json").read_text(encoding="utf-8"))
    na_by_slug = {c["slug"]: c for c in na_site["champions"]}
    cn_raw = json.loads((WEB_DATA / "cn.json").read_text(encoding="utf-8"))
    cn_by_slug = {}
    for c in cn_raw["champions"]:
        entry = c.get("byBracket", {}).get("3") or next(iter(c.get("byBracket", {}).values()), None)
        if entry:
            cn_by_slug[c["slug"]] = {"wr": entry.get("winRate")}
    hist = json.loads((WEB_DATA / "champion_change_history.json").read_text(encoding="utf-8"))
    hist_by_name = hist.get("champions", {})

    champs = [c for c in site["champions"] if c.get("wr") is not None]
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
        champs = [c for c in champs if c["name"].lower() in wanted]
    if args.limit:
        champs = champs[: args.limit]
    if not champs:
        raise SystemExit("no champions selected")

    existing = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8")).get("champions", {})

    client = None
    if not args.dry_run:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM, temperature=0.2, max_output_tokens=8000,
        )

    written, rejected = 0, []
    for i, champ in enumerate(champs, 1):
        history = hist_by_name.get(champ["name"], [])
        balance = [h for h in history if h.get("kind") == "balance" and not h.get("modeOnly")]
        days = _days_since(balance[-1].get("publishedAt")) if balance else None
        sheet, allowed = _facts(champ, na_by_slug.get(champ["slug"]),
                                cn_by_slug.get(champ["slug"]), balance, days)

        if args.dry_run:
            print(f"\n===== {champ['name']} =====\n{sheet}")
            continue

        text = None
        for attempt in range(3):
            try:
                r = client.models.generate_content(
                    model=args.model, contents=sheet, config=config)
                candidate = (r.text or "").strip()
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                if any(s in msg for s in ("RESOURCE_EXHAUSTED", "429", "503",
                                          "UNAVAILABLE", "overloaded")):
                    # Rate limit or a temporarily overloaded model: both clear
                    # on their own, and losing a champion to one wastes the
                    # whole run's worth of retries later.
                    time.sleep(min(60, 15 * (attempt + 1)))
                    continue
                print(f"  [{i}/{len(champs)}] {champ['name']}: API error {msg[:90]}")
                break
            bad = _ungrounded(candidate, allowed)
            if bad:
                print(f"  [{i}/{len(champs)}] {champ['name']}: rejected, "
                      f"unsourced number(s) {bad} -- retrying")
                continue
            text = candidate
            break

        if not text:
            rejected.append(champ["name"])
            continue
        existing[champ["slug"]] = {"text": text, "tier": champ["tier"], "wr": champ["wr"]}
        written += 1
        print(f"  [{i}/{len(champs)}] {champ['name']} ({champ['tier']}, {champ['wr']}%)")
        print(f"      {text}")

    if args.dry_run:
        return 0

    OUT.write_text(json.dumps({
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": args.model,
        "champions": existing,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {written} generated, "
          f"{len(existing)} total"
          + (f", {len(rejected)} failed: {rejected}" if rejected else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
