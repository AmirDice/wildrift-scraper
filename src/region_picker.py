"""Click-drag to pick a rectangular region from a screenshot.

Use this to find `--crop X,Y,W,H` values for OCR tuning without eyeballing
pixel coordinates in an image viewer.

Source modes:
    file    - load a saved screenshot from disk (default if you pass a path)
    device  - grab a fresh screenshot from a connected ADB device

Controls (image window focused):
    click-drag   draw a rectangle (release to finalize)
    o            run OCR on the current rectangle (winrate mode)
    c            print the crop string again
    r            in device mode, grab a fresh screenshot
    q / ESC      quit

Examples:
    python -m src.region_picker data\leaderboard_sample2.png
    python -m src.region_picker --device 127.0.0.1:7555
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import ocr as ocr_module
from .adb_client import ADBClient, ADBError
from .display import compute_fit_scale


WINDOW_NAME = "region picker  |  drag=rect  o=ocr  c=copy  r=refresh  q=quit"


@dataclass
class PickerState:
    image: np.ndarray
    scale: float = 1.0
    # In ORIGINAL image coords:
    rect: tuple[int, int, int, int] | None = None  # x, y, w, h (finalized)
    drag_start: tuple[int, int] | None = None
    drag_current: tuple[int, int] | None = None
    pending_action: str | None = None  # set by mouse callback, drained in main loop
    history: list[tuple[int, int, int, int]] = field(default_factory=list)


def to_display(pt: tuple[int, int], scale: float) -> tuple[int, int]:
    return int(round(pt[0] * scale)), int(round(pt[1] * scale))


def render(state: PickerState) -> np.ndarray:
    img = state.image.copy()

    # Draw the in-progress drag rect (while mouse is down)
    if state.drag_start is not None and state.drag_current is not None:
        x1, y1 = state.drag_start
        x2, y2 = state.drag_current
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 255), 2)

    # Draw the finalized rect
    if state.rect is not None:
        x, y, w, h = state.rect
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        label = f"x={x} y={y} w={w} h={h}"
        cv2.putText(img, label, (x, max(0, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, label, (x, max(0, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

    if state.scale != 1.0:
        new_w = int(img.shape[1] * state.scale)
        new_h = int(img.shape[0] * state.scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def on_mouse(event: int, x: int, y: int, flags: int, state: PickerState) -> None:
    # Map display coords back to original image coords.
    ox = int(round(x / state.scale))
    oy = int(round(y / state.scale))

    if event == cv2.EVENT_LBUTTONDOWN:
        state.drag_start = (ox, oy)
        state.drag_current = (ox, oy)
        state.rect = None
    elif event == cv2.EVENT_MOUSEMOVE and state.drag_start is not None:
        state.drag_current = (ox, oy)
    elif event == cv2.EVENT_LBUTTONUP and state.drag_start is not None:
        x1, y1 = state.drag_start
        x2, y2 = (ox, oy)
        rx, ry = min(x1, x2), min(y1, y2)
        rw, rh = abs(x2 - x1), abs(y2 - y1)
        # Clamp inside image
        H, W = state.image.shape[:2]
        rx = max(0, min(rx, W - 1))
        ry = max(0, min(ry, H - 1))
        rw = max(1, min(rw, W - rx))
        rh = max(1, min(rh, H - ry))
        if rw >= 3 and rh >= 3:  # ignore tiny accidental clicks
            state.rect = (rx, ry, rw, rh)
            state.history.append(state.rect)
            state.pending_action = "rect_finalized"
        state.drag_start = None
        state.drag_current = None


def print_crop(rect: tuple[int, int, int, int]) -> None:
    x, y, w, h = rect
    print(f"  --crop {x},{y},{w},{h}")


def run_ocr_on_rect(image: np.ndarray, rect: tuple[int, int, int, int], mode: str) -> None:
    x, y, w, h = rect
    crop = image[y:y + h, x:x + w]
    if mode == "winrate":
        value, result = ocr_module.read_winrate(crop)
        print(f"  ocr raw    : {result.text!r}")
        print(f"  confidence : {result.confidence:.1f}")
        print(f"  winrate    : {value}")
    else:
        result = ocr_module.read_text(crop, ocr_module.GENERAL_TESSERACT_CONFIG)
        print(f"  ocr raw    : {result.text!r}")
        print(f"  confidence : {result.confidence:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", nargs="?", type=Path, help="Saved screenshot to load. Omit to use --device.")
    parser.add_argument("--device", default=None, help="ADB device to grab from (e.g. 127.0.0.1:7555)")
    parser.add_argument("--no-connect", action="store_true", help="Skip 'adb connect' when using --device")
    parser.add_argument("--scale", type=float, default=None, help="Override display scale (e.g. 0.5). Default: auto-fit to screen.")
    parser.add_argument("--ocr-mode", choices=("winrate", "text"), default="text",
                        help="OCR mode when pressing 'o'. 'text' reads all text in the region (default); 'winrate' uses the digits/percent whitelist.")
    args = parser.parse_args()

    if args.image is None and args.device is None:
        # Default to live MuMu if neither given
        args.device = "127.0.0.1:7555"

    client: ADBClient | None = None
    if args.device is not None and args.image is None:
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
    else:
        img = cv2.imread(str(args.image))
        if img is None:
            print(f"error: could not read {args.image}", file=sys.stderr)
            return 1

    state = PickerState(image=img)
    state.scale = args.scale if args.scale is not None else compute_fit_scale(img)
    if state.scale != 1.0:
        print(f"display scaled to {state.scale:.2f}x (image is {img.shape[1]}x{img.shape[0]})")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse, state)

    print("drag a rectangle around the text. press 'o' to OCR it, 'c' to reprint the crop string.")

    while True:
        cv2.imshow(WINDOW_NAME, render(state))
        key = cv2.waitKey(20) & 0xFF

        if state.pending_action == "rect_finalized" and state.rect is not None:
            state.pending_action = None
            print(f"picked rect:")
            print_crop(state.rect)

        if key in (ord("q"), 27):
            break
        elif key == ord("o"):
            if state.rect is None:
                print("  no rectangle picked yet")
            else:
                run_ocr_on_rect(state.image, state.rect, args.ocr_mode)
        elif key == ord("c"):
            if state.rect is None:
                print("  no rectangle picked yet")
            else:
                print_crop(state.rect)
        elif key == ord("r"):
            if client is None:
                print("  refresh only works in --device mode")
            else:
                try:
                    state.image = client.screenshot()
                    if args.scale is None:
                        state.scale = compute_fit_scale(state.image)
                    state.rect = None
                    print("  refreshed screenshot")
                except ADBError as e:
                    print(f"  refresh failed: {e}")

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
