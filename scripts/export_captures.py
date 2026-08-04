"""Export completed capture sessions into the site's data files.

Two outputs, one scan:

1. data/winrates.csv -- the file the whole existing pipeline reads
   (scripts/export_json.py: site.json, tiers, history snapshots, thin
   players.json). Rows for freshly captured champions REPLACE that champion's
   old rows; champions without a new session keep their old rows so the site
   stays whole during a multi-night collection. --fresh drops all old rows
   instead (use for the patch-boundary cutover).

2. web-next/public/players/<slug>.json -- the ENRICHED per-champion
   leaderboard the new page fetches on demand: per player the ladder row
   (rank, name, score, games, winrate), identity (riot tag, ranked tier,
   level), the build actually equipped (items, runes, spells), and per-queue
   performance stats. One file per champion keeps any single fetch ~30 KB.

A champion's source session is the NEWEST capture directory whose extraction
produced at least --min-ranks rows. Partial/abandoned sessions never export.

Run after extractions finish:
    python -m scripts.export_captures            # merge into winrates.csv
    python -m scripts.export_captures --fresh    # replace winrates.csv wholesale
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.integrity import HIDDEN_LABEL, is_advertising_account  # noqa: E402

CAPTURES = ROOT / "data" / "captures"
WINRATES = ROOT / "data" / "winrates.csv"
PLAYERS_DIR = ROOT / "web-next" / "public" / "players"

CSV_COLUMNS = ["champion", "rank", "player_name", "score", "games", "winrate", "captured_at"]


def _slug(name: str) -> str:
    s = name.lower().replace("&", "and").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def _float(v):
    try:
        return round(float(v), 1)
    except (TypeError, ValueError):
        return None


def _read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def find_sessions(min_ranks: int) -> dict[str, Path]:
    """{champion: newest complete session dir}. Session time comes from the
    directory name stamp, so re-extraction never reorders sessions."""
    best: dict[str, tuple[str, Path]] = {}
    for d in sorted(CAPTURES.iterdir()) if CAPTURES.exists() else []:
        rows = _read_csv(d / "extracted.csv")
        filled = [r for r in rows if (r.get("winrate") or "").strip()]
        if len(filled) < min_ranks:
            continue
        champ = rows[0]["champion"]
        stamp = d.name.rsplit("_", 2)[-2] + d.name.rsplit("_", 2)[-1]
        if champ not in best or stamp > best[champ][0]:
            best[champ] = (stamp, d)
    return {c: p for c, (_s, p) in best.items()}


def _stats_by_rank(session: Path) -> dict[int, dict]:
    """{rank: {queueKey: compactStats}}; the READ queue label wins over the
    requested one, so a missed dropdown tap cannot mislabel a queue."""
    out: dict[int, dict] = {}
    for r in _read_csv(session / "stats.csv"):
        rank = _int(r.get("rank"))
        if rank is None:
            continue
        label = (r.get("queue") or "").strip().lower()
        key = "legendary" if "legendary" in label else "ranked"
        out.setdefault(rank, {})[key] = {
            "games": _int(r.get("games")),
            "wr": _float(r.get("win_rate")),
            "kda": _float(r.get("kda")),
            "tf": _float(r.get("teamfight_participation")),
            "gpm": _int(r.get("gold_per_minute")),
            "dmg": _int(r.get("damage_dealt_per_match")),
            "taken": _int(r.get("damage_taken_per_match")),
            "turret": _int(r.get("turret_damage_per_match")),
            "mvp": _int(r.get("mvp")),
            "sRating": _int(r.get("s_rating")),
            "aRating": _int(r.get("a_rating")),
            "legendary": _int(r.get("legendary")),
            "penta": _int(r.get("pentakill")),
            "quadra": _int(r.get("quadra_kill")),
            "triple": _int(r.get("triple_kill")),
            "firstBlood": _int(r.get("first_blood")),
        }
    return out


def _builds_by_rank(session: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    path = session / "builds.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        b = json.loads(line)
        items = [{"slug": i.get("slug"), "name": i.get("name")}
                 for i in (b.get("items") or []) if i.get("name") and i.get("name") != "?"]
        if not (items or b.get("runes") or b.get("spells")):
            continue
        out[int(b["rank"])] = {
            "items": items,
            "runes": b.get("runes") or [],
            "spells": b.get("spells") or [],
        }
    return out


def _players_by_rank(session: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in _read_csv(session / "players.csv"):
        rank = _int(r.get("rank"))
        if rank is None:
            continue
        tag = (r.get("riot_tag") or "").strip()
        out[rank] = {
            "tag": tag if tag and tag.lower() != "error" else None,
            "tier": (r.get("tier") or "").strip() or None,
            "level": _int(r.get("level")),
            "guild": (r.get("guild") or "").strip() or None,
        }
    return out


def _drop_snapback_duplicates(rows: list[dict]) -> tuple[list[dict], list[int]]:
    """Remove the same player captured twice from one leaderboard reset.

    The board snaps back to rank 1 every few profile views. When it does so
    mid-journey the scraper can re-capture a row it already has while
    believing it is deeper down, which lands the identical player -- same
    name, score, games and win rate -- under two ranks. The genuine one is
    the LOWER rank: the snap-back throws us toward the top, so the bogus copy
    is always the deeper one we thought we had reached.

    Score cannot arbitrate this. What the site stores is each player's
    HIGHEST ACHIEVED score, not their current one, so it legitimately fails
    to decrease with rank.
    """
    seen: dict[tuple, int] = {}
    dropped: list[int] = []
    keep: list[dict] = []
    for r in sorted(rows, key=lambda x: int(x["rank"])):
        name = (r.get("player_name") or "").strip()
        key = (name, r.get("score"), r.get("games"), r.get("winrate"))
        if name and key in seen:
            dropped.append(int(r["rank"]))
            continue
        if name:
            seen[key] = int(r["rank"])
        keep.append(r)
    return keep, dropped


def export_champion(champ: str, session: Path) -> tuple[list[dict], dict]:
    """(winrates.csv rows, enriched players/<slug>.json payload)."""
    rows = _read_csv(session / "extracted.csv")
    rows, dropped = _drop_snapback_duplicates(rows)
    if dropped:
        print(f"    dropped {len(dropped)} snap-back duplicate(s) at rank(s) "
              + ", ".join(str(d) for d in dropped))
    ids = _players_by_rank(session)
    builds = _builds_by_rank(session)
    stats = _stats_by_rank(session)

    csv_rows, enriched = [], []
    for r in sorted(rows, key=lambda x: int(x["rank"])):
        rank = int(r["rank"])
        if not (r.get("winrate") or "").strip():
            continue  # unextracted rank (manual-review leftovers)
        csv_rows.append({c: r.get(c, "") for c in CSV_COLUMNS})
        who = ids.get(rank) or {}
        # Boosting adverts keep their ROW (ranks stay contiguous and the board
        # stays a faithful mirror of the game) but lose their name and their
        # build: the name is the advertisement. web/integrity.py has the rest.
        hidden = is_advertising_account(r.get("player_name"))
        enriched.append({
            "r": rank,
            "p": HIDDEN_LABEL if hidden else (r.get("player_name") or ""),
            "hidden": True if hidden else None,
            "s": _int(r.get("score")),
            "g": _int(r.get("games")),
            "w": _float(r.get("winrate")),
            "tag": None if hidden else who.get("tag"),
            "tier": who.get("tier"),
            "level": who.get("level"),
            "build": None if hidden else builds.get(rank),
            "stats": None if hidden else (stats.get(rank) or None),
        })
    payload = {
        "champion": champ,
        "slug": _slug(champ),
        "capturedAt": (rows[0].get("captured_at") or "")[:10],
        "players": enriched,
    }
    return csv_rows, payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-ranks", type=int, default=45,
                    help="Extraction rows a session needs to count as complete")
    ap.add_argument("--fresh", action="store_true",
                    help="Drop ALL existing winrates.csv rows instead of merging")
    ap.add_argument("--players-only", action="store_true",
                    help="Write only the enriched players/<slug>.json files; leave "
                         "winrates.csv untouched (pre-release preview)")
    args = ap.parse_args()

    sessions = find_sessions(args.min_ranks)
    if not sessions:
        raise SystemExit("no complete extracted sessions found under data/captures")
    print(f"exporting {len(sessions)} champion(s): {', '.join(sorted(sessions))}")

    old_rows = [] if args.fresh else _read_csv(WINRATES)
    keep = [r for r in old_rows if r.get("champion") not in sessions]

    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    new_rows: list[dict] = []
    for champ, session in sorted(sessions.items()):
        csv_rows, payload = export_champion(champ, session)
        new_rows.extend(csv_rows)
        out = PLAYERS_DIR / f"{payload['slug']}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        n_builds = sum(1 for p in payload["players"] if p.get("build"))
        n_stats = sum(1 for p in payload["players"] if p.get("stats"))
        print(f"  {champ}: {len(csv_rows)} rows, {n_builds} builds, {n_stats} stat sets "
              f"({session.name}) -> {out.relative_to(ROOT)}")

    if args.players_only:
        print("\n--players-only: winrates.csv left untouched")
        return 0

    with WINRATES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for r in keep + new_rows:
            w.writerow({c: r.get(c, "") for c in CSV_COLUMNS})
    print(f"\nwinrates.csv: {len(new_rows)} fresh + {len(keep)} carried rows"
          + (" (FRESH mode: old rows dropped)" if args.fresh else ""))
    print("next: python -m scripts.export_json  (site.json, tiers, history snapshot)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
