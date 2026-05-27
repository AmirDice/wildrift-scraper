"""Interactive coordinate mapper.

Grabs a screenshot from a connected ADB device (MuMu Player on 127.0.0.1:7555
by default), displays it in a window, and lets you click to record named
(x, y) points. Saves the map to a JSON file you can reuse from the scraper.

Controls (focus must be on the image window):
    left-click  -> record a point; you'll be prompted in the terminal for a name
    u           -> undo the last recorded point
    r           -> grab a fresh screenshot (keeps existing points)
    s           -> save points to the output JSON file
    q / ESC     -> quit (prompts to save if there are unsaved changes)

Run:
    python -m src.coordinate_mapper                       # defaults
    python -m src.coordinate_mapper --device 127.0.0.1:7555 --output coords/ui_map.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .adb_client import ADBClient, ADBError


WINDOW_NAME = "wildrift coord mapper  |  click=record  u=undo  r=refresh  s=save  q=quit"
MAX_DISPLAY_W = 1600
MAX_DISPLAY_H = 900


@dataclass
class MapperState:
    image: np.ndarray
    points: dict[str, tuple[int, int]] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)  # insertion order for undo
    scale: float = 1.0
    dirty: bool = False
    pending_click: tuple[int, int] | None = None  # in original image coords


def compute_scale(img: np.ndarray) -> float:
    h, w = img.shape[:2]
    scale = min(MAX_DISPLAY_W / w, MAX_DISPLAY_H / h, 1.0)
    return scale


def render(state: MapperState) -> np.ndarray:
    img = state.image.copy()
    for name, (x, y) in state.points.items():
        cv2.circle(img, (x, y), 8, (0, 255, 0), 2)
        cv2.circle(img, (x, y), 2, (0, 255, 0), -1)
        cv2.putText(
            img, name, (x + 12, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA,
        )
        cv2.putText(
            img, name, (x + 12, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA,
        )
    if state.scale != 1.0:
        new_w = int(img.shape[1] * state.scale)
        new_h = int(img.shape[0] * state.scale)
        img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def on_mouse(event: int, x: int, y: int, flags: int, state: MapperState) -> None:
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    # Map display coords back to original image coords.
    orig_x = int(round(x / state.scale))
    orig_y = int(round(y / state.scale))
    state.pending_click = (orig_x, orig_y)


def prompt_name(existing: dict[str, tuple[int, int]]) -> str | None:
    """Ask user (in terminal) to name the just-clicked point. Empty cancels."""
    while True:
        try:
            name = input("  name (blank to cancel): ").strip()
        except EOFError:
            return None
        if not name:
            return None
        if name in existing:
            overwrite = input(f"  '{name}' exists at {existing[name]}. overwrite? [y/N]: ").strip().lower()
            if overwrite != "y":
                continue
        return name


def save_map(state: MapperState, output: Path, device: str) -> None:
    h, w = state.image.shape[:2]
    payload = {
        "device": device,
        "resolution": {"width": w, "height": h},
        "points": {name: {"x": x, "y": y} for name, (x, y) in state.points.items()},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2))
    state.dirty = False
    print(f"  saved {len(state.points)} point(s) -> {output}")


def load_existing(output: Path) -> dict[str, tuple[int, int]]:
    if not output.exists():
        return {}
    try:
        data = json.loads(output.read_text())
        return {n: (p["x"], p["y"]) for n, p in data.get("points", {}).items()}
    except (json.JSONDecodeError, KeyError, TypeError):
        print(f"  warning: could not parse existing {output}; starting fresh")
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", default="127.0.0.1:7555", help="ADB device address")
    parser.add_argument("--output", default="coords/ui_map.json", type=Path, help="JSON file to read/write")
    parser.add_argument("--no-connect", action="store_true", help="Skip 'adb connect' (device already attached)")
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

    existing = load_existing(args.output)
    if existing:
        print(f"loaded {len(existing)} existing point(s) from {args.output}")

    state = MapperState(image=img, points=existing, order=list(existing.keys()))
    state.scale = compute_scale(img)
    if state.scale != 1.0:
        print(f"display scaled to {state.scale:.2f}x (device is {img.shape[1]}x{img.shape[0]})")

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse, state)

    print("ready. click points in the window; name each one in this terminal.")

    while True:
        cv2.imshow(WINDOW_NAME, render(state))
        key = cv2.waitKey(20) & 0xFF

        if state.pending_click is not None:
            x, y = state.pending_click
            state.pending_click = None
            print(f"clicked ({x}, {y})")
            name = prompt_name(state.points)
            if name:
                if name not in state.points:
                    state.order.append(name)
                state.points[name] = (x, y)
                state.dirty = True
                print(f"  recorded '{name}' = ({x}, {y})")
            else:
                print("  cancelled")

        if key in (ord("q"), 27):
            if state.dirty:
                try:
                    ans = input("unsaved changes. save before quitting? [Y/n]: ").strip().lower()
                except EOFError:
                    ans = "n"
                if ans in ("", "y", "yes"):
                    save_map(state, args.output, args.device)
            break
        elif key == ord("s"):
            save_map(state, args.output, args.device)
        elif key == ord("u"):
            if state.order:
                last = state.order.pop()
                state.points.pop(last, None)
                state.dirty = True
                print(f"  undid '{last}'")
            else:
                print("  nothing to undo")
        elif key == ord("r"):
            try:
                state.image = client.screenshot()
                state.scale = compute_scale(state.image)
                print("  refreshed screenshot")
            except ADBError as e:
                print(f"  refresh failed: {e}")

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
