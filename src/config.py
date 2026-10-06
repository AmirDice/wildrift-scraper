"""Loaders for the per-screen coordinate JSONs + OCR regions."""
from __future__ import annotations

import json
import sys as _sys
from pathlib import Path

# Force the path to resolve absolutely relative to this file's location on disk.
# This prevents background threads and GUIs from looking in the wrong execution directory.
COORDS_DIR = Path(__file__).resolve().parent.parent / "coords"

# Persistent calibration file. Stores values learned at runtime so subsequent
# runs can skip the OCR-based alignment.
CALIBRATION_FILE: Path = COORDS_DIR / "calibration.json"


def load_calibration() -> dict:
    """Return the persisted calibration dict, or {} if file missing/invalid."""
    if not CALIBRATION_FILE.exists():
        return {}
    try:
        return json.loads(CALIBRATION_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_calibration(data: dict) -> None:
    """Merge `data` into the existing calibration file and write back."""
    existing = load_calibration()
    existing.update(data)
    CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    CALIBRATION_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")

# OCR crop region for the champion-tiles strip on screen 5.
# Format: (x, y, w, h) in device-native pixels.
# History:
#   - (573, 601, 909, 167) on the 1600x900 emulator (CHAMPION AND LANE default tab)
#   - (779, 729, 1367, 192) on the 2340x1080 phone (CHAMPION AND LANE default tab)
#   - (779, 729, 1561, 201) on the 2340x1080 phone after switching to the
#     RECENT tab — the layout is wider so tiles span more horizontally.
SCREEN_5_OCR_REGION: tuple[int, int, int, int] = (779, 729, 1561, 201)

# Player-name OCR on screen 2 (the leaderboard). The name appears in a
# fixed position relative to each row, so we crop using the row's mapped
# y plus a fixed offset/height. Tune by mapping the name rect for row 1
# (rank 1) with `python -m src.region_picker`. The printed --crop is
# (x, y, w, h); plug them in here.
#
# Phone (2340x1080) example from row 1 with player_row_1.y = 246:
#   region (1341, 196, 345, 53)
#   -> X range:  (1341, 1341+345) = (1341, 1686)
#   -> Y offset: 196 - 246 = -50 (name top sits 50px above row tap-y)
#   -> Height:   53
#
# LEFT EDGE, measured rather than eyeballed. The 1341 above came from picking
# the region by hand off one row, and it lands INSIDE the first glyph: across
# 420 sampled rows the name's first ink sits at x 1334-1343, so 1341 clipped
# 419 of them. The damage is invisible for round letters and destroys any
# first letter whose ink is a vertical stem -- "Eclipsa" read as "-clipsa",
# "Dogskii" as "Jogskii", "GGWP" as "3GWP" -- and the result still looks like
# a plausible name, so no confidence check rejected it.
#
# 1328 is the middle of the real gutter: the avatar's right edge reaches at
# most x=1322 and the earliest name ink is x=1334, so this clears every
# avatar and keeps every glyph. Leading background costs Tesseract nothing.
LEGACY_NAME_GEOMETRY = ((1328, 1686), -50, 53)
# September relayout: name above score, to the right of the avatar.
SCREEN_2_NAME_X_RANGE: tuple[int, int] = (1020, 1295)
SCREEN_2_NAME_Y_OFFSET: int = -40
SCREEN_2_NAME_HEIGHT: int = 40

# OCR region for the big champion-name label at lower-left of screen 2
# (e.g. "AATROX") used to verify the bot didn't open the wrong leaderboard page.
SCREEN_2_LABEL_REGION: tuple[int, int, int, int] = (90, 890, 240, 60)

# How many player rows fit on screen 2 without scrolling.
ROWS_PER_PAGE = 5

# Strip swipe anchors on screen 5 (right-to-left swipe reveals more champion
# tiles). Derived from SCREEN_5_OCR_REGION with a margin on each side.
_x, _y, _w, _h = SCREEN_5_OCR_REGION
SCREEN_5_STRIP_CENTER_Y: int = _y + _h // 2
SCREEN_5_STRIP_LEFT_X: int = _x + 30
SCREEN_5_STRIP_RIGHT_X: int = _x + _w - 30

# Rank-badge x-range on screen 2 (used by rank-verification OCR). Each row
# has a banner-shaped badge at this x-range; vertical center comes from the
# row pitch.
# 2026-09-25 relayout: the rank number moved from a banner badge at (575-695)
# to a plain gold numeral immediately left of the player avatar. Measured
# 805-855 on rank 1; the band below carries margin.
SCREEN_2_BADGE_X_RANGE: tuple[int, int] = (795, 870)
LEADERBOARD_LAYOUT = "2026-09-25"


def badge_band_plausible(candidate, reference) -> bool:
    """Whether `candidate` can be the SAME rank column as `reference`.

    ONE definition, used both when a relocation is proposed and when
    calibration.json is read back, because the two drifted apart and let the
    same bad value through twice.

    The old test was "overlaps the reference by 70% of its width", and it is
    the wrong question. The sweep window that proposes a band is 170px wide
    against a 75px reference, so it can clear 70% overlap while sitting 110px
    off centre and dragging in a column of unrelated digits. Measured against
    every band that has actually poisoned a run:

        (985,1155)  centre off 237  width 2.27x   old: rejected
        (735,905)   centre off  12  width 2.27x   old: ACCEPTED
        (685,855)   centre off  62  width 2.27x   old: ACCEPTED

    All three are rejected by asking the two questions that matter: is it
    centred on the same digits, and is it the same KIND of band. A real
    re-measure of this column shifts it slightly and keeps its width; anything
    much wider is a sweep window, not a column.
    """
    try:
        cx0, cx1 = int(candidate[0]), int(candidate[1])
        rx0, rx1 = int(reference[0]), int(reference[1])
    except (TypeError, ValueError, IndexError):
        return False
    width = rx1 - rx0
    if width <= 0 or cx1 <= cx0:
        return False
    centre_off = abs((cx0 + cx1) / 2 - (rx0 + rx1) / 2)
    return centre_off <= width / 4 and 0.8 <= (cx1 - cx0) / width <= 1.6


def resolve_badge_calibration(cal: dict, override: str | None = None):
    """Resolve current-layout geometry; explicit calibration replaces its anchor.

    Old layout coordinates cannot be trusted, but unrelated calibration values
    (fling distance, account name) are retained by save_calibration's merge.
    """
    def band(value):
        x0, x1 = map(int, value)
        if not 0 <= x0 < x1 <= 2340:
            raise ValueError("badge column must satisfy 0 <= x0 < x1 <= 2340")
        return x0, x1

    if override is not None:
        current = reference = band(override.split(","))
    elif cal.get("leaderboard_layout") != LEADERBOARD_LAYOUT:
        current = reference = SCREEN_2_BADGE_X_RANGE
    else:
        try:
            current = band((cal["badge_x0"], cal["badge_x1"]))
            reference = band(cal.get("badge_x_ref") or current)
        except (KeyError, TypeError, ValueError):
            current = reference = SCREEN_2_BADGE_X_RANGE
        # A stored band that is not plausibly this column is a poisoned file,
        # not a calibration. Fall back to the reference rather than letting it
        # ruin the run: a wrong value here is invisible in the source.
        if not badge_band_plausible(current, reference):
            print(f"[config] calibration badge column {current} is not plausibly "
                  f"the reference column {reference}; using the reference",
                  file=_sys.stderr)
            current = reference
    return current, reference, {
        "badge_x0": current[0], "badge_x1": current[1],
        "badge_x_ref": list(reference), "leaderboard_layout": LEADERBOARD_LAYOUT,
    }


def player_name_region(tap_y: int, layout: str | None = None):
    """Unversioned archived captures use the pre-relayout name geometry."""
    (x0, x1), offset, height = (
        (SCREEN_2_NAME_X_RANGE, SCREEN_2_NAME_Y_OFFSET, SCREEN_2_NAME_HEIGHT)
        if layout == LEADERBOARD_LAYOUT else LEGACY_NAME_GEOMETRY
    )
    return x0, max(0, int(tap_y) + offset), x1 - x0, height

# ---- pre-2026-09-25 geometry, kept ONLY for the archived sample frames ----
# data/2_aatrox_leaderboard.png, data/champions_page.png and the debug_scans
# frames were all captured on the old layout, so the tests that assert scanner
# BEHAVIOUR against them have to read them with the geometry they were shot
# with. Live code must never use these.
LEGACY_BADGE_X_RANGE: tuple[int, int] = (575, 695)
LEGACY_SCREEN_1_NAME_X_RANGE: tuple[int, int] = (1180, 1660)
LEGACY_SCREEN_2_CHAMP_LABEL_REGION: tuple[int, int, int, int] = (230, 845, 700, 55)

# ---- extended-capture points (phone 2340x1080, measured from flow_*.png) ----
# 2026-09-25 relayout: the book is no longer a per-row icon tapped at
# (BOOK_X, row_y). It is one button on the right-hand rail that acts on the
# CURRENTLY HIGHLIGHTED player, so the row must be tapped first to select it.
# That reverses the old order, which opened the build before touching the row.
SCREEN_2_BOOK: tuple[int, int] = (2165, 241)
# The X that closes the build popup.
SCREEN_2_BUILD_CLOSE: tuple[int, int] = (1936, 178)
# STATS tab in the profile's bottom tab bar (same bar as CHAMPION AND LANE).
SCREEN_5_STATS_TAB: tuple[int, int] = (1178, 1028)
# Stats page controls: the list-view toggle (right of the radar/list switch),
# the queue dropdown, and the dropdown's option rows when open.
STATS_LIST_TOGGLE: tuple[int, int] = (2153, 45)
STATS_QUEUE_DROPDOWN: tuple[int, int] = (1702, 45)
# Champions page (screen 1, CHAMPION tab). 2026-09-25 relayout: the rows no
# longer carry the champion NAME as text at all. Each row now shows the
# champion as a PORTRAIT only, plus that champion's rank-1 player and score,
# so champion identity has to come from icon matching (src/icon_match.py
# against web-next/public/champions) rather than OCR. The old band (1180-1660)
# now lands entirely on the splash art.
SCREEN_1_NAME_X_RANGE: tuple[int, int] | None = None
SCREEN_1_ROW_TAP_X: int = 900
# Row pitch went from 146 to 158, first row centre at y=284.
SCREEN_ROW_PITCH: int = 158
SCREEN_ROW_FIRST_Y: int = 284
#: RANKED rows only. The 2026-09 layout shows four, plus your own pinned row
#: below them -- see SCREEN_LIST_Y_RANGE and coords/screen_2.json.
SCREEN_ROW_COUNT: int = 4
# Vertical extent of the RANKED list, as opposed to the whole screen. The rank
# scanner must not look outside it, because the badge column contains digits
# at both ends that are not ranks.
#
# ABOVE: the relayout put a "Server" dropdown directly over the column, and
# the digit bank matches that capital S as a 5 at 0.63 with a 0.13 margin --
# past both thresholds. Since the scanner keys results by rank and keeps the
# topmost sighting, the phantom CLAIMED the number 5 and the real rank-5 row
# lost its position to it, pointing the tap at the header. On 8 of the 10
# frames the 2026-10-05 NA run rejected.
#
# BELOW: your own row is pinned under the list and reads "Top N%" instead of
# a rank, so for most accounts it puts a real digit in the column in the same
# font and size as a badge. Nothing about the glyph says it is not a rank.
#
# Half a row of slack at each end keeps partially scrolled rows in scope; the
# pinned row is drawn OVER the list, so a ranked row scrolled past this edge
# is hidden behind it anyway. Callers clamp this to the frame.
SCREEN_LIST_Y_RANGE: tuple[int, int] = (
    SCREEN_ROW_FIRST_Y - SCREEN_ROW_PITCH // 2,
    SCREEN_ROW_FIRST_Y + (SCREEN_ROW_COUNT - 1) * SCREEN_ROW_PITCH
    + SCREEN_ROW_PITCH // 2,
)
# Champion portrait centres: screen 1 rows and the screen 2 switcher column.
SCREEN_1_PORTRAIT_X: int = 593
SCREEN_2_PORTRAIT_X: int = 599
# Screen 2's top-left back chevron (returns to the champions page) and the
# champion-name label at the bottom-left (authoritative identity check).
SCREEN_2_BACK_POINT: tuple[int, int] = (172, 47)

# The in-app back chevron on the PROFILE screens (profile, champion and lane,
# stats, legendary stats) -- measured at (197-202, 47) on all four. Using it
# instead of SYSTEM back is what stops the profile chain ejecting the app: a
# system back with the chain one screen shallower than expected walks out of
# the leaderboard entirely and then opens the quit dialog on the main menu.
# The chevron can only ever move one level up inside the game.
PROFILE_BACK_POINT: tuple[int, int] = (200, 50)
# Wide enough for the longest names ("NUNU & WILLUMP" clipped at 260px and a
# live run skipped him); verified against every flow frame + the main menu
# that no other screen shows matchable text in this band at width 700.
# 2026-09-25 relayout: REMOVED from the UI. The bottom-left champion name that
# served as the authoritative identity check is gone; that region is now empty
# background. The replacements, in order of preference: the build popup prints
# the champion name in text (see build.jpg), and the screen 2 switcher column
# can be icon matched. Left as None so any reader fails loudly instead of
# OCRing blank art.
SCREEN_2_CHAMP_LABEL_REGION: tuple[int, int, int, int] | None = None

# Main-menu recovery: climbing back into the leaderboard after a full
# ejection. Coordinates derived from owner-supplied screenshots
# (data/menu_01_mainmenu.png, data/menu_02.png, data/exit_game.png).
# Main-menu identification. The PLAY button was the original signal and it is
# NOT reliable: it sits on a purple disc over champion art, and live frames
# read as "( pay", "cn gy", "po n ( bay". The left-hand panel is plain white
# UI text on flat chrome and reads perfectly on every captured main menu,
# including through the dimmed quit dialog. Any one signal is enough.
MAIN_MENU_PLAY_REGION: tuple[int, int, int, int] = (1950, 865, 245, 150)
MAIN_MENU_PLAY_WORDS: tuple[str, ...] = ("play", "lay")
MAIN_MENU_PANEL_REGION: tuple[int, int, int, int] = (150, 600, 400, 200)
MAIN_MENU_PANEL_WORDS: tuple[str, ...] = ("wild pass", "stellar", "event(s)", "vent(s)")
# Third signal: the account chip at top-left, which only the main menu shows.
# The name is device-specific, so it is read from coords/calibration.json
# ("profile_name") when present and ignored otherwise.
MAIN_MENU_NAME_REGION: tuple[int, int, int, int] = (300, 40, 420, 70)
MAIN_MENU_LEADERBOARD_BADGE: tuple[int, int] = (1331, 1016)  # last badge, bottom bar
LEADERBOARD_CHAMPION_TAB: tuple[int, int] = (235, 390)      # left sidebar
QUIT_DIALOG_REGION: tuple[int, int, int, int] = (809, 369, 740, 330)  # OCR: NOTICE / Quit Game?
QUIT_DIALOG_CANCEL: tuple[int, int] = (1002, 631)
# Confirm button in the same Quit Game dialog.  Keeping this beside the
# cancel point makes the maintenance restart explicit and prevents an
# accidental tap on the dimmed main-menu art.
QUIT_DIALOG_CONFIRM: tuple[int, int] = (1315, 631)
# The leaderboard ROOT screen's bottom tab bar (RANKED / CHAMPION / LANE /
# COLLECTION / GUILD). System back from a champion's leaderboard lands on the
# RANKED tab here -- which shows rank badges of its own and fooled the
# recovery into chevron-tapping its way further out.
LEADERBOARD_TAB_BAR_REGION: tuple[int, int, int, int] = (110, 245, 270, 605)

STATS_QUEUE_OPTIONS: dict[str, tuple[int, int]] = {
    "all": (1702, 109),
    "ranked": (1702, 181),
    "normal": (1702, 252),
    "legendary": (1702, 325),
}

# Safe-zone y-range on screen 2 — any rank badge whose top y is below this
# minimum (closer to the top of the screen) is partially cut off; any badge
# whose bottom y exceeds the maximum is partially cut off at the bottom.
# When a target badge isn't inside this zone, the bot does a micro-swipe to
# correct.
SCREEN_2_SAFE_Y_TOP: int = 170
SCREEN_2_SAFE_Y_BOTTOM: int = 710


def load_screen_points(n: int) -> dict[str, tuple[int, int]]:
    """Return name -> (x, y) coordinates for screen N with robust absolute pathing."""
    path = COORDS_DIR / f"screen_{n}.json"

    if not path.exists():
        print(f"\n❌ [CRITICAL CONFIG ERROR] Layout configuration file missing!")
        print(f"👉 Looked at absolute path: {path}")
        print("💡 Please verify that your JSON calibration profiles exist in your 'coords/' directory.\n")
        raise FileNotFoundError(f"Missing coordinate calibration map: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {name: (p["x"], p["y"]) for name, p in data["points"].items()}
    except Exception as e:
        print(f"\n❌ [CRITICAL READ ERROR] Failed parsing JSON contents at {path}")
        print(f"👉 System Error: {e}\n")
        raise


def first_point(points: dict[str, tuple[int, int]]) -> tuple[str, int, int]:
    """Return (name, x, y) of the first entry in a coordinates dict (insertion order)."""
    if not points:
        raise ValueError("Cannot extract coordinates from an empty points dictionary.")
    name, (x, y) = next(iter(points.items()))
    return name, x, y
