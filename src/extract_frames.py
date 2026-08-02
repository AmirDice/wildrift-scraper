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
    for e in entries:
        rank = e["rank"]
        tap_y = e.get("tap_y")
        lb_path = capture_dir / e.get("lb_frame", "")
        if tap_y is None or not lb_path.exists():
            status[rank] = "unknown"
            continue
        img = cv2.imread(str(lb_path))
        if img is None:
            status[rank] = "unknown"
            continue
        ranks_map, pitch = scan_visible_ranks(img, badge_x)
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
                f"-- stats likely belong to rank {nearest_rank} ({lb_path})"
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
        try:
            if args.engine == "gemini":
                return rank, _extract_strip_gemini(img, region, target, args.model)
            return rank, _extract_strip_tesseract(img, region, target)
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
    if args.engine == "gemini":
        for e in entries:
            rank = e["rank"]
            g_name = names.get(rank)
            tap_y = e.get("tap_y")
            lb_path = args.capture_dir / e.get("lb_frame", "")
            if not g_name or tap_y is None or not lb_path.exists() or ascii_share(g_name) < 0.7:
                continue
            img = cv2.imread(str(lb_path))
            if img is None:
                continue
            x0, x1 = SCREEN_2_NAME_X_RANGE
            region = (x0, max(0, int(tap_y) + SCREEN_2_NAME_Y_OFFSET), x1 - x0, SCREEN_2_NAME_HEIGHT)
            t_name = read_player_name(img, region)
            if not t_name or ascii_share(t_name) < 0.7:
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
