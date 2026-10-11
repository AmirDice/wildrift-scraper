"""Capture the champion loadout panel from the CN companion app.

Capture-only, like the leaderboard pipeline: this writes frames and a
manifest, nothing else. Reading them is scripts/extract_loadouts.py, so a
parser fix never costs another pass on the phone.

WHAT IT DOES NOT DO: find the champion. The app's navigation is not mapped,
so you open a champion's info screen yourself and this walks the five tabs
from there. That keeps the risky, app-version-specific part in your hands
and the repeatable part here.

Every captured frame is verified against the tab it was supposed to land on
by reading the underline bar. A tap that misses would otherwise re-capture
the previous tab five times and look like a clean run.

Set the app's rank filter BEFORE capturing and pass what you set: 经典
(Classic) is ranked, and the panel reports whichever ranks that filter
includes. The same champion reads ~42% on the default view and 48.72% on the
public Diamond+ endpoint for the same date, so a capture whose bracket is not
recorded cannot be compared with anything.

Run:
    python -m scripts.scrape_loadouts --champion Milio --bracket challenger
    python -m scripts.scrape_loadouts --champion Milio --bracket all --device <serial>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adb_client import ADBClient, ADBError
from src import loadouts as L

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "data" / "captures_loadouts"

#: EVERY tab is scrolled while its list is still running off the bottom edge.
#: This used to be a fixed set containing only the first tab, which was wrong:
#: whether a tab overflows depends on the champion and the bracket, not the
#: tab. At 峡谷之巅 Shen's equipment fits in 4 rows while Jax's exceeds the 11
#: a screen holds, and the fixed set truncated Jax's equipment and runes while
#: reporting a clean capture.
MAX_SCROLL_FRAMES = 10


#: Mean absolute difference, in grey levels, below which the table body is
#: taken to be unchanged. MEASURED on Shen: 0.000 between two frames showing
#: the same rows, and 9.0 to 23.0 between two that scrolled. The threshold
#: sits in a gap nine times wider than the signal it has to catch.
STILL_MAD = 1.0

#: The table body as a fraction of frame height. Above it sit the tab strip
#: and the column headers, which do not move when the list scrolls; below it
#: is the same edge is_truncated measures against.
BODY_Y = (0.30, L.TRUNCATION_Y)


def _table_body(frame: np.ndarray) -> np.ndarray:
    h = frame.shape[0]
    return frame[int(BODY_Y[0] * h):int(BODY_Y[1] * h), :]


def _same_table(a, b) -> bool:
    """Did that swipe move the list, or is this the same rows again?

    Compares the TABLE BODY, not the whole screenshot. The check used to be
    `(nxt == frame).all()` over the entire frame and it never once fired:
    two grabs of an unchanged list still differ by 0.006 to 0.054 grey
    levels SOMEWHERE outside the table, so every finished list ran on to
    the 10-frame cap and saved copies of its last screen until it got
    there. Of Shen's 38 captured frames 16 were duplicates, and each one
    cost a screenshot here and a read during extraction.
    """
    if a is None or b is None:
        return False
    pa, pb = _table_body(a), _table_body(b)
    if pa.shape != pb.shape:
        return False
    return float(np.abs(pa.astype(np.int16) - pb.astype(np.int16)).mean()) < STILL_MAD


def _settle(client: ADBClient, want: str, attempts: int = 3):
    """Screenshot until the frame actually shows `want`, else give up."""
    for i in range(attempts):
        time.sleep(0.6 + 0.4 * i)        # lists animate in; let them land
        frame = client.screenshot()
        if L.detect_active_tab(frame) == want:
            return frame
    return None


def capture_champion(client: ADBClient, champion: str, out_dir: Path,
                     bracket: str, mode: str, lane: str,
                     lanes_available: list[str] | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "champion": champion,
        # The rank filter the app was set to. Required, because these numbers
        # are meaningless without it: the panel's default view puts Milio at
        # ~42% where the public Diamond+ endpoint has him at 48.72% on the
        # same date, and the only thing that reconciles them is which ranks
        # were included. A capture with no bracket recorded cannot be placed
        # against any other dataset we hold, so there is no "unknown" option.
        "bracket": bracket,
        # 经典 (Classic) is RANKED. The chips under the champion name are a
        # filter, and on the 2026-10-08 sample none of them was highlighted --
        # which is the panel sitting on its unfiltered default and reporting
        # normals. That is what put Milio at ~42% against 48.72% on the public
        # ranked endpoint for the same date, and the tell was that his builds
        # carried no support item.
        #
        # NOT VERIFIED FROM THE FRAME YET, unlike the active tab: we have no
        # capture showing a SELECTED chip, so there is nothing to match
        # against. Until there is, this is your word for it. See
        # L.MODE_CHIPS_Y for where the detector will read.
        "mode": mode,
        "modeVerified": False,
        "lane": lane,
        # Every lane this champion's own dropdown offered, so the dataset
        # records how many roles the champion has rather than leaving it to
        # be inferred from which directories happen to exist. Shen offers
        # 上单 and 打野; Senna 下路 and 辅助; most champions one. A capture
        # whose lane is not in this list was taken under a filter the
        # champion does not have, which is a navigation bug, not a datum.
        "lanesAvailable": list(lanes_available or []),
        # 对位 (who you lane against) or 最佳拍档 (who you duo with). It follows
        # the LANE, not the champion: the same champion played support and
        # played top fills this slot with opposite relationships. Derived here
        # and VERIFIED against the frame during extraction.
        "versusKind": L.versus_kind_for_lane(lane),
        "capturedAt": datetime.now().isoformat(timespec="seconds"),
        "referenceFrame": list(L.REFERENCE_FRAME),
        "tabs": {},
        "warnings": [],
    }

    probe = client.screenshot()
    h, w = probe.shape[:2]
    manifest["frameSize"] = [w, h]
    if abs((w / h) - (L.REFERENCE_FRAME[0] / L.REFERENCE_FRAME[1])) > 0.02:
        manifest["warnings"].append(
            f"frame {w}x{h} is not the 1080x2340 portrait aspect the geometry "
            f"was measured on; rows may be mis-cropped")

    for tab in L.TAB_ORDER:
        x = round(L.TAB_CENTERS_X[tab] * w)
        y = round(L.TAB_TAP_Y * h)
        client.tap(x, y)
        frame = _settle(client, tab)
        if frame is None:
            manifest["warnings"].append(f"{tab}: tab never became active, skipped")
            print(f"  ! {tab:9s} tap did not land, skipped")
            continue

        frames = []
        path = out_dir / f"{tab}_00.png"
        cv2.imwrite(str(path), frame)
        frames.append(path.name)
        n_rows = len(L.find_rows(frame))

        # Swipe up over the table body, not the tab strip, or the gesture
        # switches tabs instead of scrolling the list.
        #
        # THE END OF A LIST IS A SWIPE THAT CHANGES NOTHING, not a last row
        # sitting high on the screen. A finished list often ends with its last
        # row hard against the bottom edge, which is indistinguishable by
        # position from one that continues -- measured, these frames end at
        # 95.7% either way. Using position as the terminator reported correct
        # captures as truncated. is_truncated only decides whether to TRY
        # another swipe; the swipe's own result decides whether we are done.
        i = 1
        hit_cap = False
        while L.is_truncated(frame):
            if i >= MAX_SCROLL_FRAMES:
                hit_cap = True
                break
            nxt = None
            for attempt in range(2):          # one retry: a swipe can be eaten
                client.swipe(round(w * 0.5), round(h * 0.80),
                             round(w * 0.5), round(h * 0.45), 400)
                nxt = _settle(client, tab, attempts=2)
                if nxt is None or not _same_table(nxt, frame):
                    break
            if nxt is None or _same_table(nxt, frame):
                break                         # two swipes moved nothing: ended
            path = out_dir / f"{tab}_{i:02d}.png"
            cv2.imwrite(str(path), nxt)       # saved only once it is NEW
            frames.append(path.name)
            frame = nxt
            i += 1
        if hit_cap:
            manifest["warnings"].append(
                f"{tab}: hit the {MAX_SCROLL_FRAMES}-frame cap and the list "
                f"was still scrolling; raise MAX_SCROLL_FRAMES")

        manifest["tabs"][tab] = {"frames": frames, "rowsFirstFrame": n_rows}
        print(f"  + {tab:9s} {len(frames)} frame(s), {n_rows} rows on the first")

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--champion", required=True,
                    help="champion name, used to label the output directory")
    ap.add_argument("--lane", required=True,
                    help="the lane filter you selected, e.g. 'baron' or "
                         "'support'. It decides whether the first tab is "
                         "matchups or duo partners.")
    ap.add_argument("--mode", required=True,
                    help="the mode chip you SELECTED, e.g. 'classic-ranked'. "
                         "Leaving the chips unset reports normals, not ranked.")
    ap.add_argument("--bracket", required=True,
                    help="the rank filter the app is currently set to, e.g. "
                         "'challenger' or 'all'. Recorded as provenance; set it "
                         "in the app first and pass what you set.")
    ap.add_argument("--device", default=ADBClient.device,
                    help="adb device (USB serial, or IP:port for an emulator)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    client = ADBClient(device=args.device)
    try:
        client.connect()
    except ADBError as exc:
        print(f"adb: {exc}", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    slug = f"{args.mode.lower()}_{args.bracket.lower()}".replace(" ", "-")
    out_dir = args.out / f"{args.champion.lower()}_{slug}_{stamp}"
    print(f"capturing {args.champion}  mode={args.mode}  "
          f"bracket={args.bracket}  lane={args.lane}")
    print(f"  -> {out_dir}")
    print("  (open the champion's info screen AND select the mode chip first;")
    print("   an unset chip reports normals, not ranked)")
    m = capture_champion(client, args.champion, out_dir, args.bracket,
                         args.mode, args.lane)

    got = len(m["tabs"])
    for warn in m["warnings"]:
        print(f"  ! {warn}")
    print(f"done: {got}/5 tabs -> {out_dir}")
    return 0 if got == 5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
