"""Offline extractor for --capture-only sessions.

Reads the manifest a capture session wrote, pulls winrate/score/games out of
each saved strip frame (and player names out of the leaderboard frames), and
writes a CSV in the same schema as the live scraper. Ranks whose strip frame
does not show the target champion are left blank in the CSV and listed in
needs_manual.txt with their exact frame paths, so the manual pass is a short
worklist instead of a hunt.

Because the frames stay on disk, extraction is re-runnable: fix a prompt or a
parser, run again, nothing needs re-scraping.

Run:
    python -m src.extract_frames data/captures/aatrox_20260802_1710
    python -m src.extract_frames data/captures/aatrox_20260802_1710 --engine tesseract
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from . import champions as champ_module
from .config import (
    SCREEN_2_BADGE_X_RANGE,
    SCREEN_2_NAME_HEIGHT,
    SCREEN_2_NAME_X_RANGE,
    SCREEN_2_NAME_Y_OFFSET,
    SCREEN_5_OCR_REGION,
    load_calibration,
)
from .ocr import (
    find_champion_winrates,
    find_target_data,
    locate_badge_column,
    read_player_name,
    scan_visible_ranks,
)
from .storage import CSVWriter, LeaderboardRow


def _load_manifest(capture_dir: Path) -> list[dict]:
    """Last entry per rank wins (a retried rank overwrote its frames too)."""
    path = capture_dir / "manifest.jsonl"
    if not path.exists():
        raise SystemExit(f"error: no manifest.jsonl in {capture_dir}")
    by_rank: dict[int, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            by_rank[int(entry["rank"])] = entry
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return [by_rank[r] for r in sorted(by_rank)]


def _norm_name(s: str) -> str:
    return "".join(ch for ch in s.casefold() if ch.isalnum())


def verify_taps(
    capture_dir: Path, entries: list[dict],
) -> tuple[dict[int, str], list[str]]:
    """Prove, from the frames on disk, that each manifest rank matches the row
    that was actually tapped.

    The lb_frame is captured milliseconds before the tap, so it is ground
    truth for what was on screen at tap time. Badge-scanning it and checking
    which rank sits at tap_y catches every snap-back that happened between
    the navigation scan and the tap. Returns ({rank: 'ok'|'unknown'|'MISMATCH
    ...'}, human-readable anomaly lines).
    """
    cal = load_calibration()
    badge_x = (
        (int(cal["badge_x0"]), int(cal["badge_x1"]))
        if "badge_x0" in cal and "badge_x1" in cal
        else SCREEN_2_BADGE_X_RANGE
    )
    located = False
    status: dict[int, str] = {}
    anomalies: list[str] = []

    # Two passes. The first collects the session's row pitch (a device
    # constant) from whatever frames read cleanly; the second verifies every
    # frame with the same priors the live navigator enjoys -- the expected
    # rank as the chain hint plus the pitch band. Without them, the verifier
    # re-suffers every OCR quirk the scanner was hardened against and files
    # false mismatches on correct taps.
    pitches: list[float] = []
    images: dict[int, np.ndarray] = {}
    for e in entries:
        lb_path = capture_dir / e.get("lb_frame", "")
        if e.get("tap_y") is None or not lb_path.exists():
            continue
        img = cv2.imread(str(lb_path))
        if img is None:
            continue
        images[e["rank"]] = img
        _r, p = scan_visible_ranks(img, badge_x, hint=float(e["rank"]))
        if p:
            pitches.append(p)
    session_pitch = sorted(pitches)[len(pitches) // 2] if pitches else None

    for e in entries:
        rank = e["rank"]
        tap_y = e.get("tap_y")
        img = images.get(rank)
        if tap_y is None or img is None:
            status[rank] = "unknown"
            continue
        ranks_map, pitch = scan_visible_ranks(
            img, badge_x, hint=float(rank), expected_pitch=session_pitch)
        if not ranks_map and not located:
            # Badge column may be calibrated for a different device; find it
            # once from the frames themselves.
            rng, ranks_map, pitch = locate_badge_column(img)
            located = True
            if rng is not None:
                badge_x = rng
        if not ranks_map:
            status[rank] = "unknown"
            continue
        nearest_rank, ny = min(ranks_map.items(), key=lambda kv: abs(kv[1] - int(tap_y)))
        tol = (pitch * 0.55) if pitch else 60.0
        if abs(ny - int(tap_y)) > tol:
            status[rank] = "unknown"
        elif nearest_rank == rank:
            status[rank] = "ok"
        else:
            status[rank] = f"MISMATCH: tapped the rank-{nearest_rank} row"
            anomalies.append(
                f"rank {rank:>3}: lb_frame shows rank {nearest_rank} at the tap position "
                f"-- stats likely belong to rank {nearest_rank} ({capture_dir / e.get('lb_frame', '')})"
            )
    return status, anomalies


def _extract_strip_tesseract(
    img: np.ndarray, region: tuple[int, int, int, int], target: str,
) -> tuple[float | None, int | None, int | None]:
    found = find_champion_winrates(img, region)
    if any(c.lower() == target.lower() for c in found.keys()):
        return find_target_data(img, region, target)
    return (None, None, None)


def _extract_strip_gemini(
    img: np.ndarray, region: tuple[int, int, int, int], target: str, model: str,
) -> tuple[float | None, int | None, int | None]:
    from .gemini_ocr import read_strip

    x, y, w, h = region
    for t in read_strip(img[y:y + h, x:x + w], model=model):
        canonical = champ_module.match(t.champion.split())
        if canonical is not None and canonical.lower() == target.lower():
            return (t.win_rate, t.score, t.games)
    return (None, None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("capture_dir", type=Path, help="A --capture-only session directory")
    parser.add_argument("--engine", choices=("gemini", "tesseract"), default="gemini",
                        help="Strip/name extractor. gemini also reads CJK player names.")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--workers", type=int, default=4, help="Parallel frame reads")
    parser.add_argument("--output", type=Path, default=None,
                        help="CSV path (default: <capture_dir>/extracted.csv)")
    args = parser.parse_args()

    entries = _load_manifest(args.capture_dir)
    if not entries:
        raise SystemExit("error: manifest is empty")
    target = entries[0]["champion"]
    out_csv = args.output or (args.capture_dir / "extracted.csv")
    print(f"{len(entries)} rank(s) in manifest | target: {target} | engine: {args.engine}")

    if args.engine == "gemini":
        # Reuse the scraper's key discovery (env var or web-next/.env.local).
        from .scrape_timed import _ensure_gemini_key
        if not _ensure_gemini_key():
            raise SystemExit("error: GEMINI_API_KEY not found; use --engine tesseract")

    # ---- names + scores from the leaderboard frames ----
    # One Gemini page read covers 4-5 ranks, so read frames until every rank
    # has a name, skipping frames whose ranks are already covered.
    names: dict[int, str] = {}
    lb_scores: dict[int, int] = {}
    if args.engine == "gemini":
        from .gemini_ocr import read_leaderboard
        for e in entries:
            if e["rank"] in names:
                continue
            lb_path = args.capture_dir / e.get("lb_frame", "")
            if not lb_path.exists():
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            try:
                for row in read_leaderboard(img, model=args.model):
                    names.setdefault(row.rank, row.player_name)
                    if row.score is not None:
                        lb_scores.setdefault(row.rank, row.score)
            except Exception as exc:  # noqa: BLE001 -- keep extracting without names
                print(f"  [names] {lb_path.name}: {exc}")
    else:
        for e in entries:
            lb_path = args.capture_dir / e.get("lb_frame", "")
            tap_y = e.get("tap_y")
            if not lb_path.exists() or tap_y is None:
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            x0, x1 = SCREEN_2_NAME_X_RANGE
            region = (x0, max(0, int(tap_y) + SCREEN_2_NAME_Y_OFFSET), x1 - x0, SCREEN_2_NAME_HEIGHT)
            name = read_player_name(img, region)
            if name:
                names[e["rank"]] = name
    print(f"names resolved: {len(names)}/{len(entries)}")

    # ---- winrate/score/games from the strip frames (parallel) ----
    def extract_one(e: dict) -> tuple[int, tuple[float | None, int | None, int | None]]:
        rank = e["rank"]
        path = args.capture_dir / e["strip_frame"]
        img = cv2.imread(str(path))
        if img is None:
            return rank, (None, None, None)
        region = tuple(e.get("strip_region") or SCREEN_5_OCR_REGION)  # type: ignore[arg-type]
        # A miss is only believed after the OTHER engine confirms it: Gemini
        # occasionally drops visible tiles (retried first -- flaky misses
        # collapse under retries), and Tesseract sees through an entirely
        # different pipeline. A frame is only "target not visible" when both
        # agree.
        try:
            if args.engine == "gemini":
                for _attempt in range(2):
                    triple = _extract_strip_gemini(img, region, target, args.model)
                    if triple[0] is not None:
                        return rank, triple
                return rank, _extract_strip_tesseract(img, region, target)
            triple = _extract_strip_tesseract(img, region, target)
            if triple[0] is not None:
                return rank, triple
            try:
                return rank, _extract_strip_gemini(img, region, target, args.model)
            except Exception:  # noqa: BLE001 -- no key/network: keep the miss
                return rank, triple
        except Exception as exc:  # noqa: BLE001 -- a bad frame shouldn't kill the batch
            print(f"  [strip] rank {rank}: {exc}")
            return rank, (None, None, None)

    results: dict[int, tuple[float | None, int | None, int | None]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for rank, triple in pool.map(extract_one, entries):
            results[rank] = triple
            wr = triple[0]
            print(f"  rank {rank:>3}: {'wr=' + str(wr) if wr is not None else 'TARGET NOT VISIBLE'}")

    # ---- correlation verification: prove name<->stats joins from the frames ----
    # 1. Tap verification: the badge at tap_y in the pre-tap frame must read
    #    the manifest rank. Catches snap-backs between navigation and tap.
    tap_status, anomalies = verify_taps(args.capture_dir, entries)
    tap_ok = sum(1 for s in tap_status.values() if s == "ok")
    tap_unknown = sum(1 for s in tap_status.values() if s == "unknown")

    # 2. Name agreement: Tesseract's independent read of the name crop at
    #    tap_y should agree with Gemini's page read for that rank. Two readers
    #    on the same pixels agreeing is strong evidence the name is right.
    #    Only meaningful for mostly-ASCII names (Tesseract garbles CJK).
    ascii_share = lambda s: sum(c.isascii() for c in s) / max(1, len(s))  # noqa: E731

    def _looks_like_a_name(s: str) -> bool:
        """Tesseract failure output ('oe eee iar immm Ae') is mostly-ASCII and
        sailed past a plain ASCII-share filter, filing 7 false disagreements
        against perfectly good Gemini names in one run. A usable read has a
        real word in it and is not mostly whitespace fragments."""
        if ascii_share(s) < 0.7 or s.count(" ") / max(1, len(s)) > 0.3:
            return False
        return bool(re.search(r"[A-Za-z0-9]{4}", s))

    if args.engine == "gemini":
        for e in entries:
            rank = e["rank"]
            g_name = names.get(rank)
            tap_y = e.get("tap_y")
            lb_path = args.capture_dir / e.get("lb_frame", "")
            # Tesseract is only a fair second witness for pure-ASCII names;
            # any diacritic or CJK in the true name guarantees a garbage
            # Tesseract read and a meaningless "disagreement".
            if not g_name or tap_y is None or not lb_path.exists() \
                    or any(not c.isascii() for c in g_name):
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            x0, x1 = SCREEN_2_NAME_X_RANGE
            region = (x0, max(0, int(tap_y) + SCREEN_2_NAME_Y_OFFSET), x1 - x0, SCREEN_2_NAME_HEIGHT)
            t_name = read_player_name(img, region)
            if not t_name or not _looks_like_a_name(t_name):
                continue
            ratio = difflib.SequenceMatcher(None, _norm_name(t_name), _norm_name(g_name)).ratio()
            if ratio < 0.5:
                anomalies.append(
                    f"rank {rank:>3}: name disagreement -- Tesseract read {t_name!r}, "
                    f"Gemini read {g_name!r} ({lb_path})"
                )

    # 3. Duplicate players: the same name under two manifest ranks means a
    #    snap-back was scraped twice under different assumed ranks.
    manifest_ranks = {e["rank"] for e in entries}
    by_name: dict[str, list[int]] = {}
    for r in manifest_ranks:
        n = names.get(r)
        if n:
            by_name.setdefault(_norm_name(n), []).append(r)
    for norm, rs in by_name.items():
        if norm and len(rs) > 1:
            anomalies.append(
                f"ranks {sorted(rs)}: same player name {names[rs[0]]!r} under multiple ranks "
                f"-- probable snap-back re-scrape; keep one, re-check the rest"
            )

    # ---- write CSV + review worklist ----
    if out_csv.exists():
        out_csv.unlink()  # extraction is re-runnable; stale rows would duplicate
    writer = CSVWriter(out_csv)
    missing: list[dict] = []
    found = 0
    for e in entries:
        rank = e["rank"]
        wr, sc, gm = results.get(rank, (None, None, None))
        if sc is None:
            sc = lb_scores.get(rank)
        if wr is not None:
            found += 1
        else:
            missing.append(e)
        writer.write(LeaderboardRow(
            champion=target,
            rank=rank,
            player_name=names.get(rank, ""),
            score=sc,
            games=gm,
            winrate=wr,
            captured_at=e.get("captured_at", ""),
        ))

    # ---- extended frames: rank popup, stats pages, build popups ----
    # All optional (present only when the capture ran with --stats/--builds).
    # Each write their own artifact next to extracted.csv.
    def _read_frame_file(name: str | None):
        if not name:
            return None
        fp = args.capture_dir / name
        return cv2.imread(str(fp)) if fp.exists() else None

    if args.engine == "gemini":
        from .gemini_ocr import read_build_popup, read_rank_popup, read_stats_page

        # canonical item-slug resolution against the site's item catalog
        items_path = Path(__file__).resolve().parent.parent / "data" / "items.json"
        item_canon: dict[str, str] = {}
        if items_path.exists():
            _norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())  # noqa: E731
            for it in json.loads(items_path.read_text(encoding="utf-8")):
                item_canon[_norm(it["name"])] = it["slug"]
                item_canon.setdefault(_norm(it["slug"]), it["slug"])

        def resolve_item(name: str) -> str | None:
            c = re.sub(r"[^a-z0-9]", "", name.lower())
            if c in item_canon:
                return item_canon[c]
            for cand in (c.rstrip("s"), c + "s"):
                if cand in item_canon:
                    return item_canon[cand]
            hits = {slug for cc, slug in item_canon.items() if c and (c in cc or cc in c)}
            return hits.pop() if len(hits) == 1 else None

        def extract_extras(e: dict) -> tuple[int, dict | None, dict[str, dict], dict | None]:
            rank = e["rank"]
            popup = stats = build = None
            stats_by_queue: dict[str, dict] = {}
            img = _read_frame_file(e.get("popup_frame"))
            if img is not None:
                try:
                    popup = read_rank_popup(img, model=args.model)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [popup] rank {rank}: {exc}")
            for queue, fn in (e.get("stats_frames") or {}).items():
                img = _read_frame_file(fn)
                if img is None:
                    continue
                try:
                    stats_by_queue[queue] = read_stats_page(img, model=args.model)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [stats/{queue}] rank {rank}: {exc}")
            img = _read_frame_file(e.get("build_frame"))
            if img is not None:
                try:
                    build = read_build_popup(img, model=args.model)
                except Exception as exc:  # noqa: BLE001
                    print(f"  [build] rank {rank}: {exc}")
            return rank, popup, stats_by_queue, build

        has_extras = any(e.get("popup_frame") or e.get("stats_frames") or e.get("build_frame")
                         for e in entries)
        if has_extras:
            import csv as _csv
            popups: dict[int, dict] = {}
            stats_rows: list[dict] = []
            builds: list[dict] = []
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                for rank, popup, stats_by_queue, build in pool.map(extract_extras, entries):
                    if popup:
                        popups[rank] = popup
                    for queue, st in stats_by_queue.items():
                        st["_rank"], st["_requested_queue"] = rank, queue
                        stats_rows.append(st)
                    if build:
                        build["_rank"] = rank
                        builds.append(build)

            if popups:
                with (args.capture_dir / "players.csv").open("w", encoding="utf-8", newline="") as f:
                    w = _csv.writer(f)
                    w.writerow(["rank", "player_name", "riot_tag", "tier", "level", "guild"])
                    for r in sorted(popups):
                        pp = popups[r]
                        w.writerow([r, pp.get("player_name") or names.get(r, ""),
                                    pp.get("riot_tag"), pp.get("tier"),
                                    pp.get("level"), pp.get("guild")])
                print(f"players.csv : {len(popups)} rows (tier/level/tag)")

            if stats_rows:
                cols = ["rank", "queue", "requested_queue", "games", "win_rate", "kda",
                        "teamfight_participation", "gold_per_minute",
                        "damage_dealt_per_match", "damage_taken_per_match",
                        "turret_damage_per_match", "mvp", "s_rating", "a_rating",
                        "legendary", "pentakill", "quadra_kill", "triple_kill", "first_blood"]
                mismatched = 0
                with (args.capture_dir / "stats.csv").open("w", encoding="utf-8", newline="") as f:
                    w = _csv.writer(f)
                    w.writerow(cols)
                    for st in sorted(stats_rows, key=lambda x: (x["_rank"], x["_requested_queue"])):
                        shown = str(st.get("queue") or "").lower()
                        req = st["_requested_queue"]
                        # 'legendary' request must show 'Legendary Ranked';
                        # 'ranked' must show plain 'Ranked'
                        ok_q = ("legendary" in shown) == (req == "legendary")
                        if not ok_q:
                            mismatched += 1
                        w.writerow([st["_rank"], st.get("queue"), req,
                                    st.get("games"), st.get("win_rate"), st.get("kda"),
                                    st.get("teamfight_participation"), st.get("gold_per_minute"),
                                    st.get("damage_dealt_per_match"), st.get("damage_taken_per_match"),
                                    st.get("turret_damage_per_match"), st.get("mvp"),
                                    st.get("s_rating"), st.get("a_rating"), st.get("legendary"),
                                    st.get("pentakill"), st.get("quadra_kill"),
                                    st.get("triple_kill"), st.get("first_blood")])
                note = f" ({mismatched} queue mismatches -- check dropdown taps)" if mismatched else ""
                print(f"stats.csv   : {len(stats_rows)} rows{note}")

            if builds:
                with (args.capture_dir / "builds.jsonl").open("w", encoding="utf-8") as f:
                    for b in sorted(builds, key=lambda x: x["_rank"]):
                        items = [{"name": n, "slug": resolve_item(str(n)) if n and n != "?" else None}
                                 for n in (b.get("items") or [])]
                        f.write(json.dumps({
                            "rank": b["_rank"],
                            "position_shown": b.get("position"),
                            "champion": b.get("champion"),
                            "player_name": b.get("player_name"),
                            "spells": b.get("spells"),
                            "runes": b.get("runes"),
                            "items": items,
                        }, ensure_ascii=False) + chr(10))
                unresolved = sum(1 for b in builds for n in (b.get("items") or [])
                                 if n and n != "?" and resolve_item(str(n)) is None)
                print(f"builds.jsonl: {len(builds)} builds ({unresolved} unresolved item names)")

    report = args.capture_dir / "needs_manual.txt"
    sections: list[str] = []
    if missing:
        sections.append("TARGET NOT VISIBLE -- read these frames by hand and fill the blank CSV rows:\n"
                        + "\n".join(f"  rank {e['rank']:>3}: {args.capture_dir / e['strip_frame']}"
                                    for e in missing))
    if anomalies:
        sections.append("CORRELATION ANOMALIES -- name and stats may not belong together:\n"
                        + "\n".join(f"  {a}" for a in anomalies))
    if sections:
        report.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    elif report.exists():
        report.unlink()

    print(f"\nextracted    : {found}/{len(entries)} ranks")
    print(f"tap-verified : {tap_ok} ok, {tap_unknown} unverifiable, "
          f"{len(entries) - tap_ok - tap_unknown} MISMATCHED")
    print(f"CSV          : {out_csv}")
    if sections:
        print(f"review       : {len(missing)} missing + {len(anomalies)} anomaly item(s) -> {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
