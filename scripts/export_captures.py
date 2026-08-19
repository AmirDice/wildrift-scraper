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

REGIONS. --region na reads data/captures_na and writes region-suffixed
outputs (data/winrates_na.csv, players/na/<slug>.json). Nothing is shared with
EU: a region that overwrote another region's rows would silently republish one
ladder's numbers under the other's name, and the capture directories are
already separate for the same reason.

Run after extractions finish:
    python -m scripts.export_captures            # EU, merge into winrates.csv
    python -m scripts.export_captures --fresh    # replace winrates.csv wholesale
    python -m scripts.export_captures --region na
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

from src.tiers import canonical_tier  # noqa: E402
from web.integrity import (  # noqa: E402
    HIDDEN_LABEL, ban_reason, is_advertising_account, is_banned_account)

# Per-region source and destinations. EU keeps the unsuffixed paths every
# other script already reads; a new region gets its own everything.
REGIONS = {
    "eu": {
        "captures": ROOT / "data" / "captures",
        "winrates": ROOT / "data" / "winrates.csv",
        "players": ROOT / "web-next" / "public" / "players",
        "index": ROOT / "web-next" / "public" / "player-index.json",
    },
    "na": {
        "captures": ROOT / "data" / "captures_na",
        "winrates": ROOT / "data" / "winrates_na.csv",
        "players": ROOT / "web-next" / "public" / "players" / "na",
        "index": ROOT / "web-next" / "public" / "player-index-na.json",
    },
}

CAPTURES = REGIONS["eu"]["captures"]
WINRATES = REGIONS["eu"]["winrates"]
PLAYERS_DIR = REGIONS["eu"]["players"]
INDEX_FILE = REGIONS["eu"]["index"]

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


#: Names transcribed by eye, for the rows neither reader could supply. Keyed by
#: capture session directory then rank. See the file's own _why.
_NAME_OVERRIDES: dict[str, dict[str, str]] = json.loads(
    (ROOT / "data" / "player_name_overrides.json").read_text(encoding="utf-8")
).get("overrides", {}) if (ROOT / "data" / "player_name_overrides.json").exists() else {}


def _players_by_rank(session: Path) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in _read_csv(session / "players.csv"):
        rank = _int(r.get("rank"))
        if rank is None:
            continue
        tag = (r.get("riot_tag") or "").strip()
        out[rank] = {
            # The popup's NAME, which until now was read and thrown away. It is
            # the better of the two readings we already hold -- see the note in
            # export_champion.
            "name": (r.get("player_name") or "").strip() or None,
            "tag": tag if tag and tag.lower() != "error" else None,
            # Canonicalised on the way out as well as on the way in, so
            # sessions extracted before the tier rules existed are cleaned
            # without re-running their extraction. A sub-Diamond reading is
            # the player's Adventure rank sitting in the ranked slot, not a
            # Gold player in a champion's top 50.
            "tier": canonical_tier(r.get("tier")),
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

    csv_rows, enriched, renamed = [], [], 0
    for r in sorted(rows, key=lambda x: int(x["rank"])):
        rank = int(r["rank"])
        # THE NAME COMES FROM THE POPUP WHERE WE HAVE ONE.
        #
        # Two readings of every player exist. extracted.csv holds Tesseract on
        # a narrow crop of the leaderboard row; players.csv holds the model's
        # read of the rank popup, which is captured for the tier/level/guild
        # anyway. Across 5921 players they disagreed on 66%, and 41% of those
        # differed in the FIRST CHARACTER ALONE -- the signature of a crop that
        # started inside the first glyph (fixed in config, but only for
        # captures taken after it). The popup read is right in every case
        # checked by hand, and it is the only one of the two that survives CJK
        # and accented characters at all.
        #
        # Set on the row itself rather than only on the output, so the advert
        # and ban checks below test the real name too: a mangled name evades
        # both, and those lists are matched against what the player actually
        # calls themselves.
        best = (_NAME_OVERRIDES.get(session.name) or {}).get(str(rank))             or (ids.get(rank) or {}).get("name")
        if best and best != (r.get("player_name") or "").strip():
            renamed += 1
            r["player_name"] = best
        has_wr = bool((r.get("winrate") or "").strip())
        # A rank whose win rate never extracted still gets its ROW. It used to
        # be dropped here, which made the gaps invisible: the board renumbered
        # around them and there was no way to see WHOSE number was missing --
        # exactly the thing you need to know to go and read it by hand.
        # winrates.csv still only takes rows with a number, because a blank one
        # contributes nothing to a statistic.
        if has_wr:
            csv_rows.append({c: r.get(c, "") for c in CSV_COLUMNS})
        who = ids.get(rank) or {}
        # Boosting adverts keep their ROW (ranks stay contiguous and the board
        # stays a faithful mirror of the game) but lose their name and their
        # build: the name is the advertisement. web/integrity.py has the rest.
        hidden = is_advertising_account(r.get("player_name"))
        # A permabanned account keeps its NAME and its row. The advert loses
        # its name because the name IS the advertisement; a ban is the
        # opposite -- the reader is better served knowing which account it
        # was. What it loses is the credit for its number, everywhere it
        # would otherwise be counted.
        banned = is_banned_account(r.get("player_name"))
        enriched.append({
            "r": rank,
            "p": HIDDEN_LABEL if hidden else (r.get("player_name") or ""),
            "hidden": True if hidden else None,
            "banned": True if banned else None,
            "banReason": ban_reason(r.get("player_name")) if banned else None,
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
    if renamed:
        print(f"    {renamed} name(s) taken from the rank popup over the leaderboard OCR")
    return csv_rows, payload


def tag_hash(tag: str | None) -> str | None:
    """FNV-1a 32-bit of the folded riot tag, or None.

    The tag is a SEARCH KEY, never a published field. Shipping it in plaintext
    would turn player-index.json into a tag directory that anyone can download
    -- exactly what showing tags on the page would do, only worse, because it
    is machine-readable and complete. Storing the hash keeps the "search by
    #tag if you already know it" behaviour while the file itself reveals none.

    FNV rather than a crypto hash because the client has to compute the same
    value from what the user typed, and this is obfuscation, not secrecy: tags
    are short enough that anyone determined could enumerate the space. It stops
    the index being a bulk source of tags, which is the actual concern.
    """
    folded = re.sub(r"\s+", "", (tag or "")).lower()
    if not folded:
        return None
    h = 0x811C9DC5
    for ch in folded:
        h = ((h ^ ord(ch)) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def build_player_index(payloads: list[dict]) -> dict:
    """One searchable record per player, across every champion board.

    The per-champion files answer "who is best at Vayne". This answers the
    other direction -- "what is this player good at" -- which is only visible
    once the boards are joined, because a strong player shows up on several.

    Joined on the display name. There is no account id in any of this: the
    boards print a name and sometimes a riot tag, so the name IS the key.
    That means two different people sharing a name would merge, which is why
    the tag is carried and shown wherever the game gave us one.

    Boosting adverts are omitted entirely rather than listed without a name.
    Their rows stay on the champion boards so the ladder is still a faithful
    mirror, but making them FINDABLE is the one thing the policy exists to
    prevent -- the name is the advertisement.
    """
    by_name: dict[str, dict] = {}
    for payload in payloads:
        slug = payload["slug"]
        for p in payload["players"]:
            if p.get("hidden"):
                continue
            name = (p.get("p") or "").strip()
            if not name:
                continue
            rec = by_name.setdefault(name.casefold(), {
                "n": name, "th": None, "tier": None, "lv": None, "c": [],
            })
            # Identity fields repeat per board; keep the first non-empty and
            # prefer the highest level seen, since it only ever goes up.
            # `th` is the HASHED tag -- see tag_hash. There is deliberately no
            # plaintext tag field anywhere in this file.
            rec["th"] = rec["th"] or tag_hash(p.get("tag"))
            rec["tier"] = rec["tier"] or p.get("tier")
            if p.get("level") is not None:
                rec["lv"] = max(rec["lv"] or 0, int(p["level"]))
            rec["c"].append({
                "s": slug, "r": p.get("r"), "w": p.get("w"),
                "g": p.get("g"), "sc": p.get("s"),
            })
    for rec in by_name.values():
        rec["c"].sort(key=lambda e: (e["r"] is None, e["r"]))
    players = sorted(by_name.values(), key=lambda r: (-len(r["c"]), r["n"].casefold()))
    return {"players": players}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    # 40, down from 45. The bar exists to skip credit-starved sessions whose
    # extraction failed wholesale -- those read 0-27 rows, so 40 still rejects
    # every one of them. What 45 was ALSO rejecting was five boards (ashe,
    # draven, gragas, nasus, sivir) sitting at 42-44 because a handful of taps
    # missed: real data, owner-accepted (2026-08-06), and while they were shut
    # out the site served their June rows instead -- older AND fewer.
    ap.add_argument("--min-ranks", type=int, default=40,
                    help="Extraction rows a session needs to count as complete")
    ap.add_argument("--fresh", action="store_true",
                    help="Drop ALL existing winrates.csv rows instead of merging")
    ap.add_argument("--players-only", action="store_true",
                    help="Write only the enriched players/<slug>.json files; leave "
                         "winrates.csv untouched (pre-release preview)")
    ap.add_argument("--region", default="eu", choices=sorted(REGIONS),
                    help="Which region's captures to export (default: eu)")
    args = ap.parse_args()

    # Rebind the module-level paths to the requested region. Every helper
    # below reads these globals, so one rebinding covers the whole export and
    # no function needs to thread a region argument through.
    global CAPTURES, WINRATES, PLAYERS_DIR, INDEX_FILE
    paths = REGIONS[args.region]
    CAPTURES, WINRATES = paths["captures"], paths["winrates"]
    PLAYERS_DIR, INDEX_FILE = paths["players"], paths["index"]
    print(f"region: {args.region.upper()}  (captures: {CAPTURES.relative_to(ROOT)})")

    sessions = find_sessions(args.min_ranks)
    if not sessions:
        raise SystemExit(f"no complete extracted sessions found under {CAPTURES.relative_to(ROOT)}")
    print(f"exporting {len(sessions)} champion(s): {', '.join(sorted(sessions))}")

    old_rows = [] if args.fresh else _read_csv(WINRATES)
    keep = [r for r in old_rows if r.get("champion") not in sessions]

    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)
    new_rows: list[dict] = []
    payloads: list[dict] = []
    for champ, session in sorted(sessions.items()):
        csv_rows, payload = export_champion(champ, session)
        new_rows.extend(csv_rows)
        payloads.append(payload)
        out = PLAYERS_DIR / f"{payload['slug']}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        n_builds = sum(1 for p in payload["players"] if p.get("build"))
        n_stats = sum(1 for p in payload["players"] if p.get("stats"))
        print(f"  {champ}: {len(csv_rows)} rows, {n_builds} builds, {n_stats} stat sets "
              f"({session.name}) -> {out.relative_to(ROOT)}")

    index = build_player_index(payloads)
    INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    multi = sum(1 for p in index["players"] if len(p["c"]) > 1)
    print(f"\nplayer-index.json: {len(index['players'])} players "
          f"({multi} on more than one board) -> {INDEX_FILE.relative_to(ROOT)}")

    if args.players_only:
        print("--players-only: winrates.csv left untouched")
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
