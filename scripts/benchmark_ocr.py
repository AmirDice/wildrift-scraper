"""Benchmark Tesseract and PaddleOCR on saved strip captures.

The benchmark uses values already written by a prior extraction as a reference
only; it does not mutate CSVs. PaddleOCR is optional, so the script reports a
clear unavailable status instead of making a capture batch fail.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402

from src.config import SCREEN_5_OCR_REGION  # noqa: E402
from src.ocr import find_target_data  # noqa: E402


def _sessions(root: Path, limit: int) -> list[Path]:
    rows = [p for p in sorted(root.iterdir())
            if p.is_dir() and (p / "manifest.jsonl").exists()
            and (p / "extracted.csv").exists()]
    return rows[:limit] if limit else rows


def _reference(session: Path) -> dict[int, float]:
    path = session / "extracted.csv"
    out: dict[int, float] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                rank = int(row.get("rank") or 0)
                value = float(row.get("win_rate") or row.get("winrate") or "")
            except (TypeError, ValueError):
                continue
            if rank and 0 <= value <= 100:
                out[rank] = value
    return out


def _entries(session: Path) -> list[dict]:
    by_rank: dict[int, dict] = {}
    for line in (session / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            by_rank[int(item["rank"])] = item
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return list(by_rank.values())


def run(root: Path, limit: int) -> dict:
    sessions = _sessions(root, limit)
    results = []
    for backend in ("tesseract", "paddle"):
        os.environ["OCR_ENGINE"] = backend
        started = time.perf_counter()
        total = correct = attempted = 0
        found = 0
        latencies: list[float] = []
        unavailable = None
        for session in sessions:
            session_entries = _entries(session)
            target = str(session_entries[0].get("champion") or
                          session.name.rsplit("_", 1)[0]) if session_entries else ""
            reference = _reference(session)
            for entry in session_entries:
                rank = int(entry["rank"])
                if rank not in reference:
                    continue
                frame = session / str(entry.get("strip_frame") or "")
                image = cv2.imread(str(frame))
                if image is None:
                    continue
                region = tuple(entry.get("strip_region") or SCREEN_5_OCR_REGION)
                t0 = time.perf_counter()
                try:
                    got, _score, _games = find_target_data(image, region, target)
                except Exception as exc:  # noqa: BLE001 -- report backend status
                    unavailable = f"{type(exc).__name__}: {exc}"
                    break
                latencies.append(time.perf_counter() - t0)
                attempted += 1
                if got is not None:
                    found += 1
                    if abs(float(got) - reference[rank]) <= 0.11:
                        correct += 1
            if unavailable:
                break
        results.append({
            "backend": backend,
            "sessions": len(sessions),
            "attempted": attempted,
            "found": found,
            "exactOrWithinPointOne": correct,
            "accuracy": round(correct / attempted, 4) if attempted else None,
            "meanSeconds": round(statistics.mean(latencies), 4) if latencies else None,
            "p95Seconds": round(sorted(latencies)[max(0, int(len(latencies) * .95) - 1)], 4)
            if latencies else None,
            "elapsedSeconds": round(time.perf_counter() - started, 2),
            "unavailable": unavailable,
        })
    return {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "root": str(root), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--captures", default="data/captures")
    parser.add_argument("--limit", type=int, default=10,
                        help="number of extracted sessions to sample")
    parser.add_argument("--out", default="reports/ocr_backend_benchmark.json")
    args = parser.parse_args()
    report = run(ROOT / args.captures, args.limit)
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
