"""Geometry and row-finding for the champion loadout panel.

This is the CN companion app's champion info screen (资讯详情), not the game.
It carries what the leaderboard capture cannot: what the whole population
builds on a champion and how each choice performs. Five tabs, one shape --
every row is (entity, win rate, pick rate):

    对位/最佳拍档  versus  1 portrait, name beside it  <- SEE BELOW
    核心装备       equip   3 item icons, CN names below
    二级鞋         boots   1 item icon, CN name below
    符文           runes   5 rune icons, no labels
    技能           skills  2 ability icons, no labels

The first tab is TWO DIFFERENT DATASETS wearing one slot. On a solo laner it
is 对位, the champions you lane AGAINST; on a support it is 最佳拍档, the
champions you duo WITH. Shen top shows 对位 and Milio shows 最佳拍档. Beating
Nasus and pairing with Kalista are opposite relationships, so the kind has to
be recorded per capture or the two silently merge into one meaningless table.
The tab's own CN label is the only thing that distinguishes them; the column
header reads 英雄 either way.

IMPORTANT: these frames are PORTRAIT. The leaderboard pipeline's
_REFERENCE_FRAME is (2340, 1080) because the game renders landscape; this
panel is a phone app at (1080, 2340). Do not share constants between them.

Rows are FOUND, not assumed. Measured, the pitch is the same 6.15% of frame
height on all five tabs -- the item labels fit inside it rather than adding to
it, so the tabs differ in row COUNT, not spacing. The reason to detect anyway
is scrolling: a tab whose list runs past the bottom edge is captured in more
than one frame, and the second frame starts at an arbitrary offset that no
fixed pitch can predict. So we project ink down the win-rate column, which
sits at the same x on all five tabs (the 胜率/登场率 headers do not move), and
let the rows fall out of it.
"""
from __future__ import annotations

import numpy as np
from pathlib import Path

#: Portrait phone frame these fractions were measured on. Everything below is
#: a FRACTION of width/height, so a different device resolution needs no
#: recalibration as long as the aspect ratio holds.
REFERENCE_FRAME = (1080, 2340)

# ---------------------------------------------------------------- columns --
#: Column bands as (x0, x1) fractions of width. Measured off the equip tab and
#: checked against the other four: the rank, 胜率 and 登场率 columns are in the
#: same place on every tab, which is what lets one row-finder serve all five.
RANK_X = (0.050, 0.135)
ENTITY_X = (0.165, 0.610)
WINRATE_X = (0.630, 0.795)
PICKRATE_X = (0.805, 0.965)

# ------------------------------------------------------------ header boxes --
#: (x0, y0, x1, y1) fractions. The champion name is "明烛-米利欧" style:
#: title-hyphen-name, so the mapping to our roster uses the part after the
#: hyphen (米利欧 = Milio) and treats the title as decoration.
CHAMPION_NAME_BOX = (0.120, 0.108, 0.650, 0.140)
#: "最近更新：20261006". Captured PER TAB on purpose: the tabs are not
#: refreshed together. On the 2026-10-08 sample, four tabs read 20261006 and
#: the boots tab read 20260710, three months stale. One collection date
#: stamped across all five would silently backdate four of them or
#: post-date one.
DATE_BOX = (0.330, 0.296, 0.720, 0.318)
#: The tab strip, and the thin underline that marks the active tab.
TAB_BAR_Y = (0.205, 0.235)
TAB_UNDERLINE_Y = (0.232, 0.241)
#: Mode chips under the champion name. NOTE: on the 2026-10-08 sample all
#: three render identically with no selected state, which means they are
#: metadata tags (the modes this champion exists in), NOT a filter. Kept here
#: so the extractor can assert that and fail loudly if a build ever does
#: highlight one, because that would change what the table below means.
MODE_CHIPS_Y = (0.150, 0.182)

#: Tab order left to right, and how many icons each row carries.
TABS = {
    "versus": {"cn": "对位/最佳拍档", "icons": 1, "labels": "beside"},
    "equip":  {"cn": "核心装备",      "icons": 3, "labels": "below"},
    "boots":  {"cn": "二级鞋",        "icons": 1, "labels": "below"},
    "runes":  {"cn": "符文",          "icons": 5, "labels": None},
    "skills": {"cn": "技能",          "icons": 2, "labels": None},
}
TAB_ORDER = ["versus", "equip", "boots", "runes", "skills"]

#: Which dataset the first tab is showing, by its CN label.
VERSUS_KINDS = {"对位": "matchup", "最佳拍档": "partners"}

#: Lanes whose first tab is 最佳拍档 (who you duo WITH) rather than 对位 (who
#: you lane AGAINST).
PARTNER_LANES = {"support", "辅助"}


def versus_kind_for_lane(lane: str) -> str:
    """Which dataset the first tab holds, from the lane alone.

    Free, and capture has no other reason to load an OCR engine: reading the
    tab label instead cost a 44s PaddleOCR start-up to recognise one word per
    champion. Extraction re-reads the label off the frame and flags any
    disagreement, so this stays an assumption that gets checked rather than
    one that gets trusted.
    """
    return "partners" if lane.strip().lower() in PARTNER_LANES else "matchup"


#: The rank filter's four options, which map exactly onto the bracket keys
#: scrape_cn.py already uses against the public endpoint. Verified by reading
#: Shen off both on 20261007: Diamond+ 55.95/2.75, Challenger 55.36/6.02/1.79
#: and Legendary 56.01/4.30 matched to the second decimal, ban rate included.
#: So this panel and hero_rank_list_v2 are the same data, and the brackets are
#: the same brackets.
BRACKETS = {
    "钻石以上": ("1", "Diamond+"),
    "大师以上": ("2", "Master+"),
    "王者以上": ("3", "Challenger"),
    "峡谷之巅": ("4", "Legendary"),
}

#: Hand-measured geometry, overriding anything below it.
#:
#: Everything in this module is a fraction of the frame, so a measurement
#: taken on one screenshot holds on any resolution. The file is optional:
#: absent, the constants in this module apply exactly as before.
#:
#:   {"columns": {"rank": [x0, x1], "entity": [...], ...},
#:    "icons":   {"equip": {"centres": [0.14, 0.42, 0.70], "size": 0.26}}}
#:
#: `columns` are fractions of FRAME width. `icons.centres` and
#: `icons.size` are fractions of the ENTITY crop's width, because that is
#: the box the icons sit in -- scripts/calibrate_loadouts.py draws the
#: current values on a real frame so they can be read off and corrected.
_OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "coords" / "loadouts.json"


def _overrides() -> dict:
    try:
        import json as _json
        return _json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:      # noqa: BLE001 -- absent or malformed: use the defaults
        return {}


OVERRIDES = _overrides()


def icon_slots(tab: str) -> dict | None:
    """Hand-measured icon positions for a tab, or None to infer them."""
    spec = (OVERRIDES.get("icons") or {}).get(tab)
    if not isinstance(spec, dict):
        return None
    centres, size = spec.get("centres"), spec.get("size")
    if not centres or not isinstance(size, (int, float)):
        return None
    return {"centres": [float(c) for c in centres], "size": float(size)}


#: The lane filter. Options are per champion -- Shen offers only 上单/打野.
#:
#: THE BOT LANE HAS TWO NAMES. The hero list's sidebar tab is 下路; the lane
#: dropdown on a champion's page calls it ADC, in Latin letters. Holding
#: only 下路 here cost the entire bot lane: eighteen champions whose single
#: role is bot had a dropdown with no recognisable option in it and were
#: skipped without a word, and Vayne, Kalista and Tristana were captured in
#: their SECOND role only, because that was the only option this map could
#: read. Both spellings are the same lane, so both resolve to Dragon.
#:
#: Case and spacing vary by app version and the match is exact after a
#: strip, so the plausible renderings are all listed rather than guessed at
#: once -- an unrecognised lane is silent, which is how this hid.
LANES = {
    "上单": "Baron", "打野": "Jungle", "中单": "Mid",
    "下路": "Dragon", "辅助": "Support",
    "ADC": "Dragon", "adc": "Dragon", "AD": "Dragon",
}

#: Spellings that mean the same lane, for anything that needs ONE label per
#: lane rather than one per name (a count of distinct roles, say).
LANE_ALIASES = {"ADC": "下路", "adc": "下路", "AD": "下路"}


def canonical_lane(label: str) -> str:
    """The sidebar's name for a lane, whatever the dropdown called it."""
    label = (label or "").strip()
    return LANE_ALIASES.get(label, label)


def band(image: np.ndarray, x: tuple[float, float],
         y: tuple[float, float]) -> tuple[int, int, int, int]:
    """Fractional (x0,x1),(y0,y1) -> integer (left, top, w, h) on this image."""
    h, w = image.shape[:2]
    left, right = round(x[0] * w), round(x[1] * w)
    top, bottom = round(y[0] * h), round(y[1] * h)
    return left, top, max(0, right - left), max(0, bottom - top)


def _ink_profile(gray: np.ndarray) -> np.ndarray:
    """Per-row count of pixels bright enough to be text on this dark theme."""
    # The panel is dark grey (~#1f1f1f) with near-white digits. A fixed
    # threshold beats Otsu here: Otsu on a mostly-empty column band finds a
    # split inside the background noise and reports ink on every row.
    return (gray > 150).sum(axis=1)


def find_rows(image: np.ndarray, min_gap: int = 6) -> list[tuple[int, int]]:
    """Row bands as (top, bottom) pixel pairs, found from the win-rate column.

    Every row has exactly one "NN.NN%" in this column and the gaps between
    rows are empty, so contiguous runs of ink are the rows. Returns them top
    to bottom; the caller pairs them with rank 1..n in order.
    """
    x0, y0, w, h = band(image, WINRATE_X, (0.0, 1.0))
    col = image[:, x0:x0 + w]
    gray = col if col.ndim == 2 else np.dot(col[..., :3], [0.114, 0.587, 0.299])
    ink = _ink_profile(gray.astype(np.uint8))

    # A row's digits are ~33px tall on the reference frame; anything much
    # thinner is the column header or an antialiasing fringe.
    min_height = max(8, round(0.010 * image.shape[0]))
    rows: list[tuple[int, int]] = []
    start = None
    gap = 0
    for y, v in enumerate(ink):
        if v > 0:
            if start is None:
                start = y
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                if y - gap - start >= min_height:
                    rows.append((start, y - gap))
                start = None
    if start is not None and len(ink) - start >= min_height:
        rows.append((start, len(ink) - 1))

    # Drop anything above the table: the 胜率 header sits in this column too.
    table_top = 0.30 * image.shape[0]
    return [r for r in rows if r[0] > table_top]


#: Tab centres as fractions of width, left to right, matching TAB_ORDER.
#: Measured off the tab strip: evenly spaced at 0.10/0.30/0.50/0.70/0.90.
TAB_CENTERS_X = {name: 0.10 + 0.20 * i for i, name in enumerate(TAB_ORDER)}
#: Where to tap to switch tabs (y is the middle of the tab strip).
TAB_TAP_Y = 0.220


def detect_active_tab(image: np.ndarray) -> str | None:
    """Which tab the frame is showing, read off the underline bar.

    The active tab carries a short bright underline directly beneath its
    label. Reading it is what lets capture verify a tap landed: a mis-tap
    that silently re-captures the previous tab would otherwise write five
    frames of the same table and look like a successful run.
    """
    x0, y0, w, h = band(image, (0.0, 1.0), TAB_UNDERLINE_Y)
    strip = image[y0:y0 + h, x0:x0 + w]
    if strip.size == 0:
        return None
    gray = strip if strip.ndim == 2 else np.dot(strip[..., :3], [0.114, 0.587, 0.299])
    cols = gray.max(axis=0) > 140
    if not cols.any():
        return None
    # Longest bright run is the underline; its centre names the tab.
    best_len = best_start = run = 0
    for i, on in enumerate(cols):
        run = run + 1 if on else 0
        if run > best_len:
            best_len, best_start = run, i - run + 1
    if best_len < 0.03 * len(cols):      # too short to be an underline
        return None
    centre = (best_start + best_len / 2) / len(cols)
    name, dist = min(((n, abs(centre - cx)) for n, cx in TAB_CENTERS_X.items()),
                     key=lambda t: t[1])
    return name if dist < 0.08 else None


#: A list whose last row ends below this fraction of frame height is running
#: past the bottom edge, so there are more rows under the fold. Measured: a
#: truncated tab ends at 96.6% every time (11 rows is all that fits), while a
#: complete one stops by 84%.
TRUNCATION_Y = 0.90


def is_truncated(image: np.ndarray, rows: list | None = None) -> bool:
    """Does this frame's list continue below the bottom edge?

    Asked of EVERY tab rather than a hardcoded list of which ones scroll.
    Which tabs overflow is not a property of the tab: Shen's equipment fits in
    4 rows at 峡谷之巅 while Jax's needs more than 11, and the first version of
    this scrolled only the versus tab and silently truncated both of Jax's.
    """
    rows = find_rows(image) if rows is None else rows
    return bool(rows) and rows[-1][1] / image.shape[0] > TRUNCATION_Y


def row_cells(image: np.ndarray, row: tuple[int, int]) -> dict[str, np.ndarray]:
    """Crop one detected row into its four columns."""
    top, bottom = row
    h, w = image.shape[:2]
    # Pad slightly: find_rows measures the digits, and the icons on a
    # label-below tab extend above and below that ink.
    pad = round(0.012 * h)
    t, b = max(0, top - pad), min(h, bottom + pad)
    cols = OVERRIDES.get("columns") or {}
    out = {}
    for key, xr in (("rank", RANK_X), ("entity", ENTITY_X),
                    ("winrate", WINRATE_X), ("pickrate", PICKRATE_X)):
        band = cols.get(key)
        if isinstance(band, (list, tuple)) and len(band) == 2:
            xr = (float(band[0]), float(band[1]))
        x0, x1 = round(xr[0] * w), round(xr[1] * w)
        out[key] = image[t:b, x0:x1]
    return out


def segment_icons(entity: np.ndarray, expected: int,
                  tab: str | None = None) -> list[np.ndarray]:
    """Icon images, left to right. See icon_spans for how they are found."""
    return [entity[:, a:b] for a, b in icon_spans(entity, expected, tab)]


def icon_spans(entity: np.ndarray, expected: int,
               tab: str | None = None) -> list[tuple[int, int]]:
    """Split an entity crop into its icon images, left to right.

    Pass `tab` to allow hand-measured slots from coords/loadouts.json to
    take over; without it, or without an entry for that tab, the icons
    are found from the image as before.

    Segments on SATURATION rather than brightness. The icons are saturated
    artwork while the CN item names under them and the champion names beside
    them are white or grey, so saturation separates icon from label where a
    brightness projection would merge the two into one blob.
    """
    if entity.size == 0 or entity.ndim != 3 or expected < 1:
        return []
    import cv2
    h, w = entity.shape[:2]

    # A hand-measured panel is not a guess and is not re-derived per frame.
    slots = icon_slots(tab) if tab else None
    if slots:
        side = max(1, round(slots["size"] * w))
        out = []
        for frac in slots["centres"][:expected]:
            x0 = int(round(frac * w - side / 2))
            x0 = max(0, min(x0, w - side)) if w >= side else 0
            out.append((x0, x0 + side))
        return out
    sat = cv2.cvtColor(entity, cv2.COLOR_BGR2HSV)[..., 1]
    cols = (sat > 60).sum(axis=0) > (0.15 * h)
    runs: list[tuple[int, int]] = []
    start = None
    for i, on in enumerate(cols):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(cols)))
    if not runs:
        return []

    # An icon is square and fills the row, so the row height IS its side.
    side = min(h, w)

    # Repair split icons BEFORE counting them. A pale band down the middle
    # of one icon reads as two runs, and counting first would then treat
    # the halves as two icons and discard a real neighbour.
    merged: list[list[int]] = [list(runs[0])]
    for a, b in runs[1:]:
        if a - merged[-1][1] < side * 0.33:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    merged = [r for r in merged if r[1] - r[0] >= side * 0.25]

    if len(merged) >= expected:
        # Widest first for the pick, left-to-right for the output.
        chosen = sorted(sorted(merged, key=lambda r: r[0] - r[1])[:expected])
        centres = [(a + b) / 2 for a, b in chosen]
    else:
        # Fewer runs than the panel has icons: two icons have run together,
        # or one is too dark to register. Neither is recoverable from the
        # runs, so fall back to the geometry and cut an even pitch across
        # everything saturated.
        left, right = merged[0][0], merged[-1][1]
        pitch = (right - left) / expected
        centres = [left + pitch * (i + 0.5) for i in range(expected)]

    out = []
    for cx in centres:
        x0 = int(round(cx - side / 2))
        x0 = max(0, min(x0, w - side)) if w >= side else 0
        out.append((x0, x0 + side))
    return out


#: The leftmost tab's label, wide enough for the 4-character 最佳拍档 and the
#: 2-character 对位 alike.
VERSUS_LABEL_BOX = (0.020, 0.200, 0.205, 0.242)


def detect_versus_kind(image: np.ndarray, read_cn) -> str | None:
    """Is the first tab 对位 (matchup) or 最佳拍档 (partners)?

    Takes the CN reader as an argument rather than importing src.ocr, which
    would drag PaddleOCR into every consumer of this module -- the geometry
    here is useful without an OCR engine present.
    """
    x0, y0, w, h = band(image, (VERSUS_LABEL_BOX[0], VERSUS_LABEL_BOX[2]),
                        (VERSUS_LABEL_BOX[1], VERSUS_LABEL_BOX[3]))
    text = read_cn(image[y0:y0 + h, x0:x0 + w]) or ""
    for cn, kind in VERSUS_KINDS.items():
        if cn in text:
            return kind
    return None
