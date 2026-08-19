"""Check each champion's assigned role against what its top-50 mains actually play.

The evidence is in the captures: a player who took Smite was in the jungle, and
a player who bought a support item was the support. Those are not opinions, they
are equipment.

Rules, per the owner's spec:
  * a clear majority (>= MAJORITY) taking Smite means Jungle
  * a clear majority holding a support item means Support
  * genuinely CLOSE splits (within CLOSE_BAND of an even split) are decided by
    which group posts the higher average win rate, not by the raw count

Deliberately conservative about "close". An earlier pass treated 36% as close
and would have moved Urgot to the jungle on a minority of players -- 36 against
64 is not a coin flip, it is a clear answer.

Champions are matched by SLUG from the capture directory, not by title-casing
the name inside builds.jsonl, which turned "JARVAN IV" into "Jarvan Iv" and
failed to match the roster.

    python -m scripts.role_from_captures
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.champion_roles import roles_for  # noqa: E402

CAPTURES = ROOT / "data" / "captures"
MAJORITY = 50.0
CLOSE_BAND = 5.0          # 45-55% counts as close; outside that the count decides
MIN_PLAYERS = 20

#: Completed and starter support items. Holding one of these is the clearest
#: signal in the build that a player was the support.
SUPPORT_ITEMS = {
    "spectral-sickle", "black-mist-scythe", "bulwark-of-the-mountain",
    "harrowing-crescent", "runesteel-spaulders", "targons-buckler",
    "world-atlas", "runic-compass", "bloodsong", "celestial-opposition",
    "dream-maker", "zaz-zaks-realmspike", "solstice-sleigh", "steel-shoulderguards",
}

SLUG_TO_NAME = {c["slug"]: c["name"] for c in
                json.loads((ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))}


def sessions():
    """{champion name: newest session dir} keyed off the directory slug."""
    best: dict[str, Path] = {}
    for d in sorted(CAPTURES.iterdir()):
        if not d.is_dir() or not (d / "builds.jsonl").exists():
            continue
        slug = d.name.rsplit("_", 2)[0]
        name = SLUG_TO_NAME.get(slug)
        if name:
            best[name] = d          # sorted order means the newest wins
    return best


def evidence(session: Path):
    """(n, smite share, support-item share, win rates split by what they played)."""
    win = {}
    ex = session / "extracted.csv"
    if ex.exists():
        with ex.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    win[int(row["rank"])] = float(row["winrate"])
                except (TypeError, ValueError, KeyError):
                    continue
    n = smite = support = 0
    wr = {"jungle": [], "support": [], "lane": []}
    for line in (session / "builds.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        b = json.loads(line)
        spells = [s for s in (b.get("spells") or []) if s and s != "?"]
        items = {i.get("slug") for i in (b.get("items") or [])}
        if not spells and not items:
            continue
        n += 1
        took_smite = any("smite" in s.lower() for s in spells)
        held_support = bool(items & SUPPORT_ITEMS)
        smite += took_smite
        support += held_support
        rate = win.get(int(b["rank"]))
        if rate is not None:
            wr["jungle" if took_smite else "support" if held_support else "lane"].append(rate)
    if not n:
        return None
    return n, smite / n * 100, support / n * 100, wr


def avg(xs):
    return sum(xs) / len(xs) if xs else None


def main() -> int:
    changes, confirmed, close_calls = [], 0, []
    print(f"{'champion':<16} {'current':<8} {'n':>4} {'smite%':>7} {'support%':>9} {'verdict'}")
    for name, session in sorted(sessions().items()):
        got = evidence(session)
        if not got:
            continue
        n, smite_pct, sup_pct, wr = got
        if n < MIN_PLAYERS:
            continue
        current = roles_for(name)[0]

        top = max(smite_pct, sup_pct)
        wants = "Jungle" if smite_pct >= sup_pct else "Support"
        note = ""
        if abs(top - MAJORITY) <= CLOSE_BAND:
            # A genuine coin flip: let the win rates break the tie.
            group = "jungle" if wants == "Jungle" else "support"
            a, b = avg(wr[group]), avg(wr["lane"])
            if a is not None and b is not None:
                note = f"CLOSE {top:.0f}% -> {wants} {a:.1f}% vs lane {b:.1f}%"
                verdict = wants if a > b else current
                close_calls.append((name, note, verdict))
            else:
                verdict = current
                note = f"CLOSE {top:.0f}% but no win rates to break the tie"
        elif top >= MAJORITY:
            verdict = wants
        else:
            verdict = current

        if verdict != current:
            changes.append((name, current, verdict, smite_pct, sup_pct, n))
            flag = f"CHANGE -> {verdict}"
        else:
            confirmed += 1
            flag = "confirms" if top >= MAJORITY else ""
        if flag or note:
            print(f"{name:<16} {current:<8} {n:>4} {smite_pct:>6.0f}% {sup_pct:>8.0f}% "
                  f"{flag} {note}")

    print("")
    print(f"confirmed by the evidence: {confirmed} champions")
    print(f"CHANGES ({len(changes)}):")
    for name, old, new, s, u, n in changes:
        print(f"  {name:<16} {old} -> {new}   (smite {s:.0f}%, support items {u:.0f}%, n={n})")
    if close_calls:
        print("")
        print("close calls decided on win rate:")
        for name, note, verdict in close_calls:
            print(f"  {name:<16} {note} -> {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
