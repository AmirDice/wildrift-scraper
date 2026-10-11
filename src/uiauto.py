"""Read the on-screen UI hierarchy over ADB, so navigation targets text.

The loadout TABLES are read from pixels, because they are a rendered grid and
their numbers are what we are after. NAVIGATION is different: menus move
between app versions, and a tap at a stale coordinate does not fail, it lands
on whatever is there now. Asking the device where 查看更多 actually is costs
one dump per screen and removes that whole class of silent breakage.

This app is React Native, whose Text components back onto real TextViews, so
the hierarchy carries the labels. If a device ever returns an empty dump the
caller should say so and stop rather than fall back to guessing coordinates.

This talks to adb directly instead of going through ADBClient._run, which
runs subprocess with text=True and therefore decodes using the machine's
locale codec. The hierarchy is UTF-8 and full of Chinese, so on a Windows
cp1252 box that raised UnicodeDecodeError inside subprocess's reader thread
and handed back None. Bytes in, explicit UTF-8 out.
"""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_DEVICE_DUMP = "/sdcard/wtm_ui.xml"
_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass
class Node:
    text: str
    desc: str
    cls: str
    clickable: bool
    bounds: tuple[int, int, int, int]      # x0, y0, x1, y1

    @property
    def center(self) -> tuple[int, int]:
        x0, y0, x1, y1 = self.bounds
        return (x0 + x1) // 2, (y0 + y1) // 2

    @property
    def label(self) -> str:
        return self.text or self.desc


def _adb(client, args: list[str]) -> tuple[int, bytes, bytes]:
    """Run adb for this device and return raw bytes, never decoded text."""
    cmd = ["adb", "-s", client.device] + args
    proc = subprocess.run(cmd, capture_output=True, check=False)
    return proc.returncode, proc.stdout or b"", proc.stderr or b""


def _parse(xml: str) -> list[Node]:
    start = xml.find("<?xml")
    if start < 0:
        return []
    try:
        root = ET.fromstring(xml[start:])
    except ET.ParseError:
        return []
    out: list[Node] = []
    for el in root.iter("node"):
        m = _BOUNDS.match(el.get("bounds", ""))
        if not m:
            continue
        out.append(Node(
            text=el.get("text", "") or "",
            desc=el.get("content-desc", "") or "",
            cls=el.get("class", "") or "",
            clickable=el.get("clickable") == "true",
            bounds=tuple(int(g) for g in m.groups()),  # type: ignore[arg-type]
        ))
    return out


def dump(client, attempts: int = 3) -> list[Node]:
    """Every node on screen. Empty list means the dump failed.

    Retries rather than failing on the first miss: uiautomator refuses with
    "could not get idle state" while the screen is still animating, which is
    exactly when we ask, because we ask right after a tap.
    """
    for i in range(attempts):
        code, out, err = _adb(client, ["shell", "uiautomator", "dump", _DEVICE_DUMP])
        message = (out + err).decode("utf-8", "replace")
        if code != 0 or "ERROR" in message:
            time.sleep(0.6 + 0.4 * i)
            continue
        code, raw, _ = _adb(client, ["exec-out", "cat", _DEVICE_DUMP])
        if code != 0 or not raw:
            time.sleep(0.4)
            continue
        nodes = _parse(raw.decode("utf-8", "replace"))
        if nodes:
            return nodes
        time.sleep(0.4)
    return []


def visible(nodes: list[Node], width: int, height: int,
            top: float = 0.0, bottom: float = 1.0) -> list[Node]:
    """Only the nodes actually on screen, and therefore actually tappable.

    Android lays out a whole list and clips it, so the hierarchy reports rows
    that are scrolled far out of view -- a 39-champion lane returns all 39,
    with the last sitting near y=5800 on a 2340-tall display. Tapping that
    does nothing, or worse lands on whatever is at the clamped coordinate, so
    every tap target has to be filtered to the viewport first.

    `top` and `bottom` narrow it further as fractions of height, for keeping
    clear of a fixed header or a bottom navigation bar that would swallow the
    tap.
    """
    lo, hi = top * height, bottom * height
    out = []
    for n in nodes:
        x0, y0, x1, y1 = n.bounds
        if x1 <= x0 or y1 <= y0:          # zero-area: clamped off-screen view
            continue
        cx, cy = n.center
        if 0 <= cx <= width and lo <= cy <= hi:
            out.append(n)
    return out


def find(nodes: list[Node], *needles: str, exact: bool = False) -> Node | None:
    """First node whose label matches any needle. Topmost-leftmost wins ties."""
    hits = []
    for n in nodes:
        lab = n.label.strip()
        if not lab:
            continue
        if any(lab == s for s in needles) if exact else any(s in lab for s in needles):
            hits.append(n)
    if not hits:
        return None
    return min(hits, key=lambda n: (n.bounds[1], n.bounds[0]))


def find_all(nodes: list[Node], labels: set[str]) -> list[Node]:
    """Every node whose exact label is in `labels`, ordered down the screen."""
    hits = [n for n in nodes if n.label.strip() in labels]
    return sorted(hits, key=lambda n: (n.bounds[1], n.bounds[0]))


def on_screen(nodes: list[Node], *needles: str) -> bool:
    return find(nodes, *needles) is not None
