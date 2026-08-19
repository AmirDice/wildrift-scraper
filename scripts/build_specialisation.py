"""Per-champion specialisation, from what each top-50 player actually plays.

Writes data/champion_specialisation.json for the site export to merge in.

WHY A NEW MEASURE. The old otp_score reads the SKEW of the games distribution
inside one champion's board -- whether a few grinders pull away from their peers.
That is a property of the player pool, not of the champion, and it misfires:
Hecarim scores 78.6 on it while only 18% of a typical Hecarim main's ranked
games are actually on Hecarim. Nobody dedicates to him; a couple of people just
grind harder than the rest of his board.

The new measure answers the question directly. For each captured player we know
their games on this champion (extracted.csv) and their total ranked games across
both ranked queues (stats.csv). The share is what fraction of their ranked play
this champion is, and the champion's score is the median share across its board.

THREE SIGNALS, and they line up into readable tags:

  share        how much of a main's ranked play is this champion
  win rate     how well the champion performs
  games        how much the board plays at all

  contested    strong, low share, low volume -- the fingerprint of a champion
               people cannot get. Hecarim (60.2% wr, 18% share, games rank
               138/140) and Nidalee (56.5%, 20%, 129/140) top this, both
               predicted by the owner before the measure existed. NOTE: we hold
               no ban data, so this is a fingerprint, not proof.
  otp          high share -- boards genuinely full of specialists (Kennen 50%,
               Irelia 44%, Akshan 43%).
  comfort      high share and high volume but a sub-median win rate: people
               commit to these because they like them, not because they win
               (Katarina, Garen, Vladimir).
  generalist   low share, nothing else remarkable.

    python -m scripts.build_specialisation
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
CAPTURES = ROOT / "data" / "captures"
ARCHIVE = ROOT / "data" / "captures_archive"
OUT = ROOT / "data" / "champion_specialisation.json"

MIN_PLAYERS = 15          # below this a median share is not worth publishing
MIN_TOTAL_GAMES = 30      # a player with fewer ranked games has no meaningful share

SLUG_TO_NAME = {c["slug"]: c["name"] for c in
                json.loads((ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))}


def sessions():
    """{champion: newest session dir} across live captures and the archive."""
    best: dict[str, Path] = {}
    for root in (ARCHIVE, CAPTURES):
        if not root.exists():
            continue
        for d in sorted(root.glob("*/*")) + sorted(root.iterdir()):
            if not d.is_dir() or not (d / "extracted.csv").exists():
                continue
            name = SLUG_TO_NAME.get(d.name.rsplit("_", 2)[0])
            if name:
                best[name] = d      # later roots and later stamps win
    return best


def shares(session: Path):
    """[(share, champion games, total ranked games)] for each usable player."""
    champ_games: dict[int, int] = {}
    with (session / "extracted.csv").open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                champ_games[int(row["rank"])] = int(row["games"])
            except (TypeError, ValueError, KeyError):
                continue
    stats = session / "stats.csv"
    if not stats.exists():
        return []
    total: dict[int, int] = {}
    with stats.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            # Both ranked queues count: a player's ranked life is Ranked plus
            # Legendary Ranked, and dividing by one of them overstates the share.
            if "ranked" not in (row.get("queue") or "").lower():
                continue
            try:
                rank = int(row["rank"])
                total[rank] = total.get(rank, 0) + int(row["games"])
            except (TypeError, ValueError, KeyError):
                continue
    out = []
    for rank, games in champ_games.items():
        tg = total.get(rank)
        if not tg or not games or tg < MIN_TOTAL_GAMES or tg < games:
            continue
        out.append((min(1.0, games / tg), games, tg))
    return out


def main() -> int:
    site_path = ROOT / "web-next" / "src" / "data" / "site.json"
    site = {c["name"]: c for c in
            json.loads(site_path.read_text(encoding="utf-8"))["champions"]} \
        if site_path.exists() else {}

    records = {}
    for name, session in sorted(sessions().items()):
        rows = shares(session)
        if len(rows) < MIN_PLAYERS:
            continue
        vals = [r[0] for r in rows]
        records[name] = {
            "specialisationShare": round(statistics.median(vals) * 100, 1),
            "heavyOtpShare": round(sum(1 for v in vals if v >= 0.5) / len(vals) * 100, 1),
            "nPlayers": len(rows),
            "medianChampGames": int(statistics.median(r[1] for r in rows)),
            "medianRankedGames": int(statistics.median(r[2] for r in rows)),
        }
    if not records:
        print("no champion had enough joined rows; nothing written")
        return 1

    # Tags come from where a champion sits against the roster, not from
    # absolute cutoffs -- the whole distribution shifts between patches.
    sh = sorted(r["specialisationShare"] for r in records.values())
    # Volume means games ON THIS CHAMPION, not the player's whole ranked life.
    # Using total ranked games here made the `contested` tag fire zero times:
    # a Hecarim main has plenty of ranked games, just very few of them on
    # Hecarim, which is exactly the signal being looked for.
    gm = sorted(r["medianChampGames"] for r in records.values())
    wrs = sorted(c["wr"] for c in site.values() if c.get("wr"))
    pct = lambda arr, v: sum(1 for x in arr if x <= v) / len(arr) * 100  # noqa: E731

    for name, rec in records.items():
        wr = (site.get(name) or {}).get("wr")
        s_pct = pct(sh, rec["specialisationShare"])
        g_pct = pct(gm, rec["medianChampGames"])
        w_pct = pct(wrs, wr) if wr else 50.0
        rec["sharePercentile"] = round(s_pct)
        rec["winratePercentile"] = round(w_pct)
        rec["contestedGap"] = round(w_pct - s_pct)

        tags = []
        if s_pct >= 75:
            tags.append("otp")
        if s_pct >= 60 and g_pct >= 60 and w_pct < 50:
            tags.append("comfort")
        if w_pct >= 70 and s_pct <= 30 and g_pct <= 40:
            tags.append("contested")
        if not tags and s_pct <= 40:
            tags.append("generalist")
        rec["gamesPercentile"] = round(g_pct)
        rec["tags"] = tags
        # The replacement for otp_score: the share itself, on a 0-100 scale
        # already, so the number means something rather than being an index.
        rec["otpScore"] = rec["specialisationShare"]

    OUT.write_text(json.dumps({
        "_note": "Per-champion specialisation from captured top-50 boards. "
                 "otpScore here is the MEDIAN SHARE of a main's ranked games "
                 "spent on this champion, replacing the old games-distribution "
                 "skew score. Built by scripts/build_specialisation.py.",
        "_tags": {
            "otp": "share in the top quartile: the board is genuinely specialists",
            "comfort": "specialised and high volume but a sub-median win rate",
            "contested": "strong, low share, low volume -- looks ban-pressured, "
                         "though we hold no ban data to confirm it",
            "generalist": "low share, nothing else remarkable",
        },
        "champions": records,
    }, indent=1, ensure_ascii=False), encoding="utf-8")

    counts: dict[str, int] = {}
    for rec in records.values():
        for t in rec["tags"] or ["untagged"]:
            counts[t] = counts.get(t, 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(records)} champions")
    print(f"  tags: {counts}")
    top = sorted(records.items(), key=lambda kv: -kv[1]["otpScore"])[:6]
    print("  most specialised:")
    for name, rec in top:
        print(f"    {name:<15} {rec['otpScore']:>5.1f}%  {','.join(rec['tags']) or '-'}")
    con = sorted(records.items(), key=lambda kv: -kv[1]["contestedGap"])[:6]
    print("  highest contested gap:")
    for name, rec in con:
        print(f"    {name:<15} gap {rec['contestedGap']:>+4}  {','.join(rec['tags']) or '-'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
