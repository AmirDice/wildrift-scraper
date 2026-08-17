"""MuMu Player setup: screenshots and region scaffolding for a second device.

The scraper's coordinate system is single-profile today: coords/screen_N.json
plus the constants in src/config.py were all measured on the phone. MuMu
renders at a different resolution and layout, so before it can collect
anything it needs its own screenshot set (to measure regions from) and its
own coordinate files. This script does the tedious half of that.

    python -m scripts.mumu_setup                    # connect, report resolution, save a test shot
    python -m scripts.mumu_setup --shot main_menu   # save one named screenshot
    python -m scripts.mumu_setup --tour             # guided walk through every screen the pipeline needs
    python -m scripts.mumu_setup --scaffold         # coords/mumu/*.json prefilled by resolution scaling

Everything lands in coords/mumu/: screenshots in coords/mumu/shots/ (these are
what we measure regions from together), scaffolded coordinate files next to
them. The scaffold is a STARTING GUESS -- every point is the phone profile
scaled by the resolution ratio, and layout differences (aspect, safe areas,
MuMu's own chrome) mean each one still has to be verified against the
screenshots before a run. The files carry "_scaled_guess": true until then.

MuMu's ADB usually answers on 127.0.0.1:7555 (older) or 127.0.0.1:16384
(MuMu 12); pass --device if yours differs. USB serials work too.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.adb_client import ADBClient, ADBError  # noqa: E402

COORDS = ROOT / "coords"
MUMU = COORDS / "mumu"
SHOTS = MUMU / "shots"

# The phone profile the existing coords/screen_N.json points were measured on.
# Override with --ref-size if the phone was something else.
REF_SIZE = (2340, 1080)

# Every screen the collection pipeline touches, in the order a run meets them.
# The tour walks these; the region work happens on these files afterwards.
TOUR = [
    ("main_menu", "the game's MAIN MENU (account chip visible top-left)"),
    ("leaderboard_root", "the leaderboard ROOT (RANKED tab, bottom tab bar visible)"),
    ("champion_tab", "the CHAMPION tab of the leaderboard (champion carousel strip)"),
    ("champion_board", "ONE champion's top-50 board (rank badges + player rows)"),
    ("profile", "a PLAYER PROFILE opened from a leaderboard row"),
    ("build_popup", "the BUILD popup (book icon on a leaderboard row)"),
    ("stats_page", "the STATS page for a player"),
    ("quit_dialog", "the QUIT dialog (press system back on the main menu)"),
]


def resolution(adb: ADBClient) -> tuple[int, int]:
    out = adb._run(["shell", "wm", "size"])
    m = re.search(r"(\d+)x(\d+)", out)
    if not m:
        raise ADBError(f"could not read resolution from: {out.strip()}")
    a, b = int(m.group(1)), int(m.group(2))
    # wm size reports portrait order on most devices; the game runs landscape.
    return (max(a, b), min(a, b))


def snap(adb: ADBClient, name: str) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    frame = adb.screenshot()
    path = SHOTS / f"{name}.png"
    cv2.imwrite(str(path), frame)
    h, w = frame.shape[:2]
    print(f"  saved {path.relative_to(ROOT).as_posix()} ({w}x{h})")
    return path


def scaffold(res: tuple[int, int], ref: tuple[int, int]) -> None:
    sx, sy = res[0] / ref[0], res[1] / ref[1]
    MUMU.mkdir(parents=True, exist_ok=True)
    print(f"scaling phone profile {ref[0]}x{ref[1]} -> MuMu {res[0]}x{res[1]} "
          f"(x{sx:.3f}, y{sy:.3f})")
    for src in sorted(COORDS.glob("screen_*.json")):
        data = json.loads(src.read_text(encoding="utf-8"))
        for point in data.get("points", {}).values():
            point["x"] = round(point["x"] * sx)
            point["y"] = round(point["y"] * sy)
        data["_scaled_guess"] = True
        data["_scaled_from"] = f"{ref[0]}x{ref[1]}"
        out = MUMU / src.name
        out.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  wrote {out.relative_to(ROOT).as_posix()}")
    cal_src = COORDS / "calibration.json"
    if cal_src.exists():
        cal = json.loads(cal_src.read_text(encoding="utf-8"))
        for key in ("badge_x0", "badge_x1"):
            if isinstance(cal.get(key), (int, float)):
                cal[key] = round(cal[key] * sx)
        if isinstance(cal.get("badge_x_ref"), list):
            cal["badge_x_ref"] = [round(v * sx) for v in cal["badge_x_ref"]
                                  if isinstance(v, (int, float))]
        # fling_rows is a scroll-physics value, not a pixel: it depends on the
        # device's fling behaviour and has to be re-learned on MuMu, so it is
        # deliberately reset rather than scaled.
        cal.pop("fling_rows", None)
        cal["profile_name"] = ""  # MuMu account name differs; fill after login
        cal["_scaled_guess"] = True
        out = MUMU / "calibration.json"
        out.write_text(json.dumps(cal, indent=2), encoding="utf-8")
        print(f"  wrote {out.relative_to(ROOT).as_posix()} (fling_rows reset, profile_name blank)")
    print("\nNOTE: the scraper still reads coords/*.json directly; wiring it to a "
          "second profile happens once these guesses are verified against the "
          "screenshots. Nothing here touches the phone profile.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--device", default="127.0.0.1:7555",
                    help="ADB serial (MuMu: 127.0.0.1:7555 or 127.0.0.1:16384)")
    ap.add_argument("--shot", default="", help="save one named screenshot and exit")
    ap.add_argument("--tour", action="store_true",
                    help="guided screenshots of every screen the pipeline needs")
    ap.add_argument("--scaffold", action="store_true",
                    help="write coords/mumu/*.json scaled from the phone profile")
    ap.add_argument("--ref-size", default="",
                    help="phone reference resolution WxH the existing coords were "
                         f"measured on (default {REF_SIZE[0]}x{REF_SIZE[1]})")
    args = ap.parse_args()

    ref = REF_SIZE
    if args.ref_size:
        m = re.fullmatch(r"(\d+)x(\d+)", args.ref_size)
        if not m:
            raise SystemExit("--ref-size must look like 2340x1080")
        ref = (int(m.group(1)), int(m.group(2)))

    adb = ADBClient(device=args.device)
    try:
        adb.connect()
    except ADBError as e:
        raise SystemExit(
            f"{e}\nIf this is MuMu 12, its ADB port is often 16384: "
            "try --device 127.0.0.1:16384 (check MuMu's settings > about).")
    res = resolution(adb)
    print(f"connected: {args.device} at {res[0]}x{res[1]} (landscape)")

    if args.scaffold:
        scaffold(res, ref)
        return
    if args.shot:
        name = re.sub(r"[^a-z0-9_-]", "", args.shot.lower()) or "shot"
        snap(adb, name)
        return
    if args.tour:
        print("Guided tour: put the game on each screen, then press Enter here.\n")
        for name, description in TOUR:
            input(f"-> {name}: open {description}, then press Enter (or Ctrl+C to stop) ")
            snap(adb, name)
        print(f"\nDone: {len(TOUR)} screenshots in {SHOTS.relative_to(ROOT).as_posix()}/. "
              "Next: measure the regions on these together, then --scaffold as a starting "
              "point for the coordinate files.")
        return
    # Default: a connectivity check with one test frame.
    snap(adb, "check")
    print("MuMu answers. Next steps: --tour for the screenshot set, "
          "--scaffold for starting-point coordinate files.")


if __name__ == "__main__":
    main()
