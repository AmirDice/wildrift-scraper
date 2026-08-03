"""Cross-check Gemini's identity cards against SCRAPED top-50 player builds.

The cards are meta knowledge from a model; the capture sessions are what the
top 50 players on each champion actually equipped. Where they disagree, the
scraped ladder is the evidence and the card is the suspect. This script turns
each complete capture session into item-stat frequencies and audits its
champion's card:

  - avoid-stat contradictions: players measurably building a stat the card
    says never to build (>10% of builds) means the card is wrong -- fix the
    card, or the advisor lint will fight the real meta;
  - signature items that almost nobody equips (<15% of builds);
  - the observed stat spectrum, for eyeballing against statPriorities.

Output goes to stdout and data/identity_validation.txt for owner review.
Kayn note: scraped builds mix both forms, so Kayn is audited against the
union of the base and Rhaast cards.

Run after extractions land:
    python -m scripts.validate_champion_identity
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.export_captures import find_sessions, _builds_by_rank  # noqa: E402

IDENTITY = ROOT / "data" / "champion_identity.json"
ITEMS = {i["slug"]: i for i in json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}
OUT = ROOT / "data" / "identity_validation.txt"

# item stat key -> identity stat token (same containment as the advisor lint:
# only stats an item cannot carry incidentally count as evidence)
DEFINING = {
    "crit": "crit",
    "physicalPenFlat": "lethality",
    "healShieldPower": "healing_power",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower().replace("'s", ""))


def item_tokens(slug: str) -> set[str]:
    item = ITEMS.get(slug) or {}
    stats = item.get("stats") or {}
    out = {tok for key, tok in DEFINING.items() if key in stats}
    if "ap" in stats and item.get("category") == "Magic":
        out.add("ap")
    # A crit item that carries lethality (The Collector) is CRIT evidence,
    # not lethality-path evidence -- it rides along in crit builds. Only a
    # pure lethality item proves the lethality archetype.
    if "lethality" in out and "crit" in stats:
        out.discard("lethality")
    # Symmetrically, crit riding on a penetration item (Mortal Reminder for
    # anti-heal, LDR vs tanks) is not crit-path evidence: bruisers buy those
    # for the pen. Only pure crit items (IE, Shieldbow) prove crit.
    if "crit" in out and ("physicalPen" in stats or "physicalPenFlat" in stats):
        out.discard("crit")
    return out


def audit(champ: str, cards: list[dict], session) -> list[str]:
    builds = _builds_by_rank(session)
    slugs_per_build = [
        {i["slug"] for i in b.get("items", []) if i.get("slug")}
        for b in builds.values()
    ]
    slugs_per_build = [s for s in slugs_per_build if s]
    n = len(slugs_per_build)
    lines = [f"{champ} ({n} scraped builds, session {session.name}):"]
    if not n:
        return lines + ["  no resolvable builds"]

    avoid = set()
    for c in cards:
        avoid |= set(c.get("avoidStats") or [])
    # a token any card allows is not avoided for the union audit
    for c in cards:
        allowed = set(c.get("statPriorities") or [])
        avoid -= allowed

    for tok in sorted(avoid):
        hits = [s for s in slugs_per_build if any(tok in item_tokens(x) for x in s)]
        share = len(hits) / n
        if share > 0.10:
            example = next(x for s in hits for x in s if tok in item_tokens(x))
            lines.append(f"  CONTRADICTION: card says never {tok}, but {share:.0%} of "
                         f"builds contain a {tok} item (e.g. {example}) -- review the card")

    sig_names = [s for c in cards for s in (c.get("signatureItems") or [])]
    canon = {_norm(i["name"]): slug for slug, i in ITEMS.items()}
    for name in sig_names:
        slug = canon.get(_norm(name))
        if slug is None:
            lines.append(f"  note: signature item {name!r} not in the item catalog "
                         "(enchanted boots or stale name)")
            continue
        share = sum(1 for s in slugs_per_build if slug in s) / n
        if share < 0.15:
            lines.append(f"  weak signature: {name} appears in only {share:.0%} of builds")

    freq: dict[str, int] = {}
    for s in slugs_per_build:
        for slug in s:
            freq[slug] = freq.get(slug, 0) + 1
    top = sorted(freq.items(), key=lambda kv: -kv[1])[:8]
    lines.append("  observed core: " + ", ".join(f"{s} {c}/{n}" for s, c in top))
    if len(lines) == 2:
        lines.insert(1, "  card agrees with the ladder")
    return lines


def main() -> int:
    store = json.loads(IDENTITY.read_text(encoding="utf-8")).get("champions", {})
    sessions = find_sessions(45)
    report: list[str] = []
    audited = 0
    for champ, session in sorted(sessions.items()):
        cards = [store[k] for k in store
                 if k == champ or k.startswith(champ + " (")]
        if not cards:
            report.append(f"{champ}: no identity card yet (batch still running?)")
            continue
        audited += 1
        report.extend(audit(champ, cards, session))
        report.append("")
    text = "\n".join(report)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"audited {audited}/{len(sessions)} captured champions -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
