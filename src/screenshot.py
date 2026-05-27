"""Grab a screenshot from the connected device and save it to disk.

Useful for collecting sample images while you tune OCR or design the scraper.

Run:
    python -m src.screenshot data/leaderboard_ahri.png
    python -m src.screenshot data/raw.png --device 127.0.0.1:7555 --no-connect
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

from .adb_client import ADBClient, ADBError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("output", type=Path, help="Where to write the PNG/JPG")
    parser.add_argument("--device", default="127.0.0.1:7555", help="ADB device address")
    parser.add_argument("--no-connect", action="store_true", help="Skip 'adb connect'")
    args = parser.parse_args()

    client = ADBClient(device=args.device)
    if not args.no_connect:
        try:
            client.connect()
        except ADBError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

    try:
        img = client.screenshot()
    except ADBError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(args.output), img)
    if not ok:
        print(f"error: failed to write {args.output}", file=sys.stderr)
        return 1

    h, w = img.shape[:2]
    print(f"saved {w}x{h} -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
