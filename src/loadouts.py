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
#:   {"columns": {"rank": [x0, x1], "entity": [...], ...}}
#:
#: `columns` are fractions of FRAME width.
#:
#: There is deliberately no override for the ICON positions. There was
#: one, because the icons were being inferred badly enough to want
#: hand-measurement; they are now measured off the panel background on
#: every frame, which is both more accurate than a hand-measured constant
#: and correct on a frame that scrolled. scripts/calibrate_loadouts.py
#: draws what was measured.
_OVERRIDE_PATH = Path(__file__).resolve().parent.parent / "coords" / "loadouts.json"


def _overrides() -> dict:
    try:
        import json as _json
        return _json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:      # noqa: BLE001 -- absent or malformed: use the defaults
        return {}


OVERRIDES = _overrides()


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


#: How far either side of the measured square to keep. The art has a soft
#: edge and the square is measured off a threshold, so a couple of pixels of
#: panel are cheaper than a shaved corner.
ICON_BLEED = 2
#: A column counts as icon when this much of the row strip's height is not
#: background. 0.40 clears the CN item name underneath (sparse white glyphs,
#: well under a third of the strip) without losing a dark rune.
_ICON_FILL = 0.40
#: Channel distance from the measured background before a pixel is content.
_ICON_TOL = 18.0
#: The entity column, a little wider than ENTITY_X either side, so a grid
#: measured inside it is not clipped by the band doing the measuring.
_ICON_SCAN_X = (0.150, 0.620)
#: Row band padding. find_rows measures the win-rate DIGITS, and the icons
#: stand taller than them on every tab.
_ICON_PAD = 0.016
#: Rows at the top and bottom of a padded strip that are always panel: the
#: pad is ~37px on the reference frame and the art overhangs the digits by
#: ~25px, which leaves comfortably more than this above and below it.
_ICON_EDGE = 4
#: Plausible icon width, as a fraction of frame width. Measured: the runes
#: are the narrowest at 78/1080 = 7.2% and the items the widest at 89/1080
#: = 8.2%.
#:
#: The CEILING is the guard that matters. A tab with no data for this
#: champion renders a full-panel illustration instead of a table;
#: find_rows picks ink out of the artwork and the column vote then returns
#: one 507px-wide "icon". Without the ceiling that frame extracts nonsense
#: tiles and nothing says anything is wrong.
#:
#: The FLOOR is deliberately far below a real icon. A rune dark enough that
#: only its bright core clears the threshold measures as little as 37px, and
#: a floor set near the true width drops that column -- which costs the
#: whole frame, because the grid then has four columns where the tab has
#: five. Six of the owner's labelled references came off frames exactly
#: this happened on. Narrow columns are repaired by _snap below, not
#: rejected here.
_ICON_WIDTH = (0.020, 0.120)


def _icon_mask(strip: np.ndarray, border: bool = False) -> np.ndarray:
    """Per-pixel: is this NOT the panel background?

    Segmenting on BACKGROUND rather than saturation. The earlier version
    projected saturation, on the reasoning that the art is colourful and the
    CN captions are grey -- true, but it also made a near-grey icon
    (Perseverance, Bone Plating) invisible and let a bright caption glyph
    read as art. The background is the one thing on this panel that is
    genuinely uniform, so what is NOT it is the icon.

    The background is each strip's own median, not a constant. This panel
    shades alternate rows very slightly, and a fixed #1f1f1f marks half of
    them as content from edge to edge.
    """
    if border:
        # The fallback. The median above assumes the panel is most of the
        # strip, and on a dense page it is not: five warm icons on Jax's
        # runes tab cover more of the strip than the grey does, the median
        # lands on an icon colour, and the gaps between icons read as
        # content -- the vote returned one 508px "icon". The strip's top and
        # bottom edges are padding above and below the art and are always
        # panel, so they give the grey directly.
        edge = np.concatenate([strip[:_ICON_EDGE], strip[-_ICON_EDGE:]])
        bg = np.median(edge.reshape(-1, strip.shape[-1]), axis=0)
    else:
        bg = np.median(strip.reshape(-1, strip.shape[-1]), axis=0)
    return np.abs(strip.astype(np.float32) - bg).max(axis=2) > _ICON_TOL


def _icon_runs(flags, min_len: int, join: int) -> list[tuple[int, int]]:
    """Contiguous True runs, bridging gaps shorter than `join`."""
    out: list[tuple[int, int]] = []
    start, gap = None, 0
    for i, on in enumerate(flags):
        if on:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap > join:
                if i - gap - start >= min_len:
                    out.append((start, i - gap))
                start, gap = None, 0
    if start is not None and len(flags) - start >= min_len:
        out.append((start, len(flags) - 1))
    return out


def _row_strips(image: np.ndarray, rows: list[tuple[int, int]]):
    """(top, left, strip) for every row, over the icon scan band."""
    h, w = image.shape[:2]
    pad = round(_ICON_PAD * h)
    x0, x1 = round(_ICON_SCAN_X[0] * w), round(_ICON_SCAN_X[1] * w)
    for top, bottom in rows:
        t, b = max(0, top - pad), min(h, bottom + pad)
        yield t, x0, image[t:b, x0:x1]


def icon_grid(image: np.ndarray, rows: list[tuple[int, int]],
              expected: int | None = None,
              border: bool = False) -> list[tuple[int, int]]:
    """Icon column spans as (x0, x1) frame pixels, left to right.

    Measured over EVERY row of the frame at once rather than per row. A rune
    whose art is nearly black leaves a column barely distinguishable from the
    panel and its own row cannot see it -- the runes tab reported four slots
    of five on a third of its rows that way. Across eleven rows the slot is
    dark in one and bright in the next, and the column always shows.

    It also makes the grid one measurement per frame instead of one per row,
    which is what makes measuring it at all cheap enough to do.

    THE VOTE HAS A BLIND SPOT, and it is the most common page on the
    ladder. It works because a dark rune in one row sits beside a bright
    one in the next. A tank's runes tab opens every row on the same
    keystone, and Grasp of the Undying -- a green hand on a near-black
    square -- fills 33% of its column against a 40% threshold in all eleven
    rows at once. The column never appeared, the grid came back four wide,
    and the frame was refused whole: Dr. Mundo, Ornn, Poppy, Shen, Sion and
    Wukong all lost their runes that way, and were blamed on the capture.
    _fill_gap recovers it from the pitch the other columns establish.
    """
    if image.ndim != 3 or not rows:
        return []
    w = image.shape[1]
    acc = None
    for _t, _x0, strip in _row_strips(image, rows):
        if strip.size == 0:
            continue
        col = _icon_mask(strip, border).mean(axis=0)
        acc = col if acc is None else acc + col
    if acc is None:
        return []
    acc /= len(rows)
    spans = _icon_runs(acc > _ICON_FILL, min_len=round(0.030 * w),
                       join=round(0.006 * w))
    lo, hi = round(_ICON_WIDTH[0] * w), round(_ICON_WIDTH[1] * w)
    spans = [s for s in spans if lo <= s[1] - s[0] + 1 <= hi]
    if expected and len(spans) > expected:
        # A caption glyph that happens to stack in the same place on every
        # row can survive the vote. It cannot outvote a column of solid art,
        # so keep the widest `expected` and put them back in order.
        spans = sorted(sorted(spans, key=lambda s: s[1] - s[0],
                              reverse=True)[:expected])
    if expected and len(spans) == expected - 1:
        spans = _fill_gap(spans, acc)
    off = round(_ICON_SCAN_X[0] * w)
    return [(off + a, off + b) for a, b in _snap(spans)]


#: A recovered column must still be clearly darker-art-than-panel. Grasp of
#: the Undying measures 0.33; an empty slot measures ~0.0. This is the line
#: between "a dark icon is there" and "nothing is there", and it is far
#: below anything real and far above the noise.
_GAP_FILL = 0.15


def _fill_gap(spans: list[tuple[int, int]],
              acc: np.ndarray) -> list[tuple[int, int]]:
    """Add the ONE column the vote missed, where the pitch says it is.

    The columns are a regular grid, so the ones that were found fix where
    the missing one has to be: inside a gap twice the pitch, or one pitch
    beyond either end. Candidates are scored on the same column profile the
    vote used, and one is added only if it is clearly not empty panel --
    so a tab that genuinely has a slot missing is still refused rather than
    given an invented icon. One column, never more: two missing columns
    means the frame is wrong, not dark.
    """
    if len(spans) < 2:
        return spans
    starts = [a for a, _b in spans]
    pitch = float(np.median(np.diff(starts)))
    width = int(np.median([b - a + 1 for a, b in spans]))
    cands = []
    for (a0, _b0), (a1, _b1) in zip(spans, spans[1:]):
        if abs((a1 - a0) - 2 * pitch) < 0.15 * pitch:
            cands.append(int(round(a0 + pitch)))
    if not cands:
        cands = [int(round(starts[0] - pitch)), int(round(starts[-1] + pitch))]
    best, best_fill = None, _GAP_FILL
    for x0 in cands:
        x1 = x0 + width - 1
        if x0 < 0 or x1 >= len(acc):
            continue
        fill = float(acc[x0:x1 + 1].mean())
        if fill >= best_fill:
            best, best_fill = (x0, x1), fill
    return sorted(spans + [best]) if best else spans


def _snap(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Give every column the median width, keeping its own centre.

    The panel draws one size of icon per tab -- that is a fact about the
    layout, not a guess -- so a column that measured narrower than its
    siblings did not find a smaller icon, it found a darker one. Taking the
    median across the columns and re-centring each on itself turns a
    threshold accident back into the square that is actually there, and
    keeps the crop stable between a frame where an icon is bright and one
    where the same icon is dim.
    """
    if len(spans) < 2:
        return spans
    med = int(np.median([b - a + 1 for a, b in spans]))
    out = []
    for a, b in spans:
        c = (a + b) / 2.0
        out.append((int(round(c - med / 2)), int(round(c + med / 2)) - 1))
    return out


def icon_vertical(image: np.ndarray, rows: list[tuple[int, int]],
                  spans: list[tuple[int, int]],
                  border: bool = False) -> tuple[int, int]:
    """(offset below the padded row top, side) for this frame's icons.

    Measured once per frame, like the grid, and for the same reason: the art
    sits at the same height in every row, and a per-row measurement is at the
    mercy of whichever icon happens to be dark in that row.

    The mask is taken over the WHOLE strip and then sliced. Masking the icon
    column on its own makes the ICON the median, so the panel around it reads
    as content and every box comes back the full height of the strip.
    """
    offs, sides = [], []
    for t, x_off, strip in _row_strips(image, rows):
        if strip.size == 0:
            continue
        m = _icon_mask(strip, border)
        for sx0, sx1 in spans:
            sub = m[:, sx0 - x_off:sx1 - x_off + 1]
            vert = _icon_runs(sub.mean(axis=1) > _ICON_FILL, min_len=4, join=3)
            if not vert:
                continue
            vy0, vy1 = max(vert, key=lambda r: r[1] - r[0])
            if vy1 - vy0 + 1 < 0.6 * (sx1 - sx0 + 1):
                continue                 # a caption line, not the art
            offs.append(vy0)
            sides.append(vy1 - vy0 + 1)
    if not offs:
        side = max(s[1] - s[0] + 1 for s in spans)
        return max(0, round(_ICON_PAD * image.shape[0]) - side // 4), side
    return int(np.median(offs)), int(np.median(sides))


class IconGeometry:
    """Where this frame draws its icons. Measured once, used for every row."""

    __slots__ = ("spans", "offset", "height", "side")

    def __init__(self, spans, offset, height):
        self.spans = spans
        self.offset = offset
        #: The vertical extent actually measured. It CENTRES the square:
        #: on the item tabs the art fades at top and bottom and measures
        #: 84px tall against an 89px column, and centring on the width
        #: instead would push every item crop 2.5px down the row.
        self.height = height
        #: The square is sized by the LARGER of the two, because the width
        #: is voted across every row and the height is not, and a square cut
        #: to the shorter of them shaves the sides off a wide icon.
        self.side = max(height, max((b - a + 1 for a, b in spans),
                                    default=height))

    def __len__(self) -> int:
        return len(self.spans)

    def boxes(self, image: np.ndarray, row: tuple[int, int],
              bleed: int = ICON_BLEED) -> list[tuple[int, int, int]]:
        """(x, y, side) squares for one row, in frame pixels."""
        t = max(0, row[0] - round(_ICON_PAD * image.shape[0]))
        half = self.side / 2 + bleed
        out = []
        for sx0, sx1 in self.spans:
            cx = (sx0 + sx1 + 1) / 2
            cy = t + self.offset + self.height / 2
            out.append((int(round(cx - half)), int(round(cy - half)),
                        int(round(2 * half))))
        return out

    def tiles(self, image: np.ndarray, row: tuple[int, int],
              bleed: int = ICON_BLEED) -> list:
        """One square crop per icon; None where the box leaves the frame."""
        h, w = image.shape[:2]
        out = []
        for x, y, s in self.boxes(image, row, bleed):
            if x < 0 or y < 0 or x + s > w or y + s > h:
                out.append(None)
            else:
                out.append(image[y:y + s, x:x + s])
        return out


def measure_icons(image: np.ndarray, rows: list[tuple[int, int]],
                  expected: int | None = None):
    """This frame's icon geometry, or None when it cannot be measured.

    `expected` is the tab's icon count. Returning None rather than a partial
    grid is deliberate: a frame that yields four columns where the tab has
    five is a frame whose rows would all be cut in the wrong places, and
    extracting it anyway is how a whole tab ends up subtly wrong.
    """
    # The whole-strip median first, then the edge estimate only if that
    # fails. Not the edge estimate everywhere: every frame that measures
    # correctly today would then be cut a pixel differently, and the owner's
    # labelled references were cut from those frames.
    for border in (False, True):
        spans = icon_grid(image, rows, expected, border)
        if spans and (expected is None or len(spans) == expected):
            off, side = icon_vertical(image, rows, spans, border)
            return IconGeometry(spans, off, side)
    return None


def segment_icons(image: np.ndarray, row: tuple[int, int],
                  geom: "IconGeometry") -> list:
    """Icon images for one row, left to right."""
    return geom.tiles(image, row)


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
