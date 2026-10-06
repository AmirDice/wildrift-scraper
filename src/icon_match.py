"""Identify build-popup icons by matching them against the game's own art.

Why this exists. Asking a vision model to name these icons does not work: the
popup is 2340x1080 and each icon is about 50px, so the model answers from
memory rather than pixels. Measured on real captures, it invented rune names
that are not in the game for 17.6% of slots, and -- worse, because validation
cannot catch it -- returned wrong-but-real names the rest of the time. Reading
the same popup twice at temperature 0 agreed on only 2 of 6 builds. Cropping
and upscaling the icons helped the runes and changed nothing fundamental.

Template matching wins because the problem is not really recognition: we
already ship every candidate icon (117 items, 53 runes, 10 spells) as art, and
the popup draws them at a fixed pitch. So each slot is compared against the
catalogue directly. It is deterministic, needs no API, runs in milliseconds,
and -- the part a model cannot offer -- reports a real confidence, so an
unclear slot becomes an honest "?" instead of a confident guess.

Scoring is a masked, per-channel normalised cross-correlation:
  - the frame border is excluded (the game draws its own border and tint);
  - the bottom-left corner is excluded, where the game stamps overlays (the
    blue "refresh/upgraded" pip and the orange "N" enchant badge);
  - a slot is only accepted when it both scores well AND beats the runner-up
    by a margin, which is what makes "I am not sure" expressible.
"""
from __future__ import annotations

import functools
import json
import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "web-next" / "public"

#: slot geometry inside a 2340x1080 popup: (y0, size, x0, pitch, count)
#
# These are measured, not eyeballed, because cross-correlation is brutally
# unforgiving about alignment: the item row sat 4px high, and that alone took
# Blade of the Ruined King from 0.805 to 0.121 on a frame whose art is
# otherwise near-identical to the catalogue. It cost about one slot per build
# -- BotRK appeared in 14 of 50 Vayne builds instead of 47 -- and because an
# unresolved TRAILING slot is read as an empty one, whole sixth items were
# dropped rather than flagged.
#
# The offsets were recovered by searching dy,dx per row over Vayne and Teemo
# popups; every frame agreed (items 4,+1 and spells 2,-2), which is what
# makes them constants rather than a per-frame alignment search. Runes
# measured (0,0) at 0.999 and are left exactly as they were.
GEOMETRY = {
    "spells": (285, 90, 1244, 110, 2),
    "runes": (470, 92, 1248, 101, 5),
    "items": (646, 88, 1247, 105, 6),
}
# Note the PITCH matters as much as the origin, and fails differently: an
# origin error shifts every slot equally, a pitch error accumulates along the
# row. At 104 the item confidences fell away left to right -- 0.81, 0.83,
# 0.86, 0.65, 0.64, 0.40 -- because slot 6 sits five pitches out and was
# therefore ~5px off while slot 1 was exact. That gradient is the signature
# to look for; at 105 slot 6 scores 0.81 like the rest of the row. Runtime
# alignment cannot rescue this, since one offset cannot fix a row whose
# slots disagree about where they are.

N = 64            # comparison resolution
MARGIN = 0.12     # fraction of the tile edge ignored (game-drawn border)
MIN_SCORE = 0.22  # below this, no candidate is credible
MIN_GAP = 0.06    # winner must beat the runner-up by this much


def _load_art(rel: str) -> np.ndarray | None:
    p = PUBLIC / rel.lstrip("/")
    im = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.ndim == 3 and im.shape[2] == 4:      # flatten alpha onto the popup's dark panel
        a = im[:, :, 3:4].astype(np.float32) / 255.0
        im = (im[:, :, :3] * a + np.full_like(im[:, :, :3], 20) * (1 - a)).astype(np.uint8)
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    return im


def _norm_tile(im: np.ndarray) -> np.ndarray:
    return cv2.resize(im, (N, N), interpolation=cv2.INTER_AREA).astype(np.float32)


@functools.lru_cache(maxsize=1)
def templates() -> dict[str, dict[str, np.ndarray]]:
    """{"items"|"runes"|"spells": {name: normalised template}}."""
    out: dict[str, dict[str, np.ndarray]] = {"items": {}, "runes": {}, "spells": {}}

    items = json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))
    for it in items:
        art = _load_art(it.get("icon") or "")
        if art is not None:
            out["items"][it["name"]] = _norm_tile(art)

    # Item OVERLAY bank: templates harvested from captured frames for art the
    # catalogue does not carry. The support income items are the reason this
    # exists -- the catalogue holds only the FINAL forms (Black Mist Scythe,
    # Bulwark of the Mountain) while the game draws whatever upgrade stage the
    # player had, so mid-tier art matched nothing and 8 of 50 Lux support
    # builds lost their support item to an honest "?". Keys may carry a
    # "#stage" suffix ("Black Mist Scythe#1"): extra looks of the SAME item.
    # match_slot folds suffixed keys into their base name when scoring.
    item_bank = ROOT / "data" / "icon_bank" / "items.npz"
    if item_bank.exists():
        with np.load(item_bank) as z:
            for name in z.files:
                out["items"][name] = z[name].astype(np.float32)

    # Runes come from the BANK -- templates averaged from the game's own
    # rendering of each rune, built by scripts/build_icon_bank.py from
    # owner-labelled clusters. The shipped catalogue art is drawn differently
    # (square, different zoom and backgrounds) and tops out around 3/5; the
    # bank matches at 0.98-0.999 because it is the same pixels the game draws.
    bank = ROOT / "data" / "icon_bank" / "runes.npz"
    if bank.exists():
        with np.load(bank) as z:
            for name in z.files:
                out["runes"][name] = z[name].astype(np.float32)
    else:                                    # fall back to catalogue art
        rune_map = ROOT / "web-next" / "src" / "data" / "rune_icons.json"
        if rune_map.exists():
            for name, icon in json.loads(rune_map.read_text(encoding="utf-8")).items():
                art = _load_art(icon)
                if art is not None:
                    out["runes"][name] = _norm_tile(art)

    spells = ROOT / "web-next" / "src" / "data" / "spells.json"
    if spells.exists():
        for s in json.loads(spells.read_text(encoding="utf-8")):
            art = _load_art(s.get("icon") or "")
            if art is not None:
                out["spells"][s["name"]] = _norm_tile(art)
    return out


@functools.lru_cache(maxsize=8)
def _weights(mask_badge: bool, circular: bool = False) -> np.ndarray:
    """Which pixels count. Runes are drawn as CIRCLES with a tree-coloured
    ring, while the catalogue art is square, so comparing the corners scores
    ring colour instead of the symbol -- a circular window fixed rune
    matching outright."""
    w = np.ones((N, N), np.float32)
    if circular:
        yy, xx = np.mgrid[0:N, 0:N]
        r = np.sqrt((yy - (N - 1) / 2) ** 2 + (xx - (N - 1) / 2) ** 2)
        w[r > N * 0.40] = 0.0
    else:
        m = int(N * MARGIN)
        w[:m], w[-m:], w[:, :m], w[:, -m:] = 0, 0, 0, 0
    if mask_badge:
        # the game stamps its overlay pips over the bottom-left of the art
        w[int(N * 0.66):, :int(N * 0.58)] = 0.0
    return w


def _score(tile: np.ndarray, w: np.ndarray, template: np.ndarray) -> float:
    total = 0.0
    denom = w.sum()
    for ch in range(3):
        x, y = tile[:, :, ch], template[:, :, ch]
        xd = (x - (x * w).sum() / denom) * w
        yd = (y - (y * w).sum() / denom) * w
        total += float((xd * yd).sum() / (np.sqrt((xd ** 2).sum() * (yd ** 2).sum()) + 1e-6))
    return total / 3.0


def match_slot(tile: np.ndarray, kind: str) -> tuple[str, float, float, str]:
    """(name_or_?, score, gap, runner_up) for one cropped slot.

    Scores fold to the BASE name first ("Black Mist Scythe#1" counts as
    "Black Mist Scythe" at its best stage's score). Without the fold, two
    stages of the same item occupy first and second place, the winner's gap
    over "the runner-up" collapses to ~0, and the confidence gate rejects an
    item precisely because the bank knows it too well.
    """
    cands = templates()[kind]
    if not cands or tile.size == 0:
        return "?", 0.0, 0.0, ""
    t = _norm_tile(tile)
    w = _weights(True, kind == "runes")
    best: dict[str, float] = {}
    for name, tpl in cands.items():
        base = name.split("#")[0]
        s = _score(t, w, tpl)
        if s > best.get(base, -9.0):
            best[base] = s
    ranked = sorted(((s, n) for n, s in best.items()), reverse=True)
    (s1, n1), (s2, n2) = ranked[0], ranked[1] if len(ranked) > 1 else (0.0, "")
    gap = s1 - s2
    ok = s1 >= MIN_SCORE and gap >= MIN_GAP
    return (n1 if ok else "?"), s1, gap, n2


def _align(image: np.ndarray, kind: str, fy: float, fx: float) -> tuple[int, int]:
    """The row's real (dy, dx) in this popup, refined from the nominal
    geometry.

    Alignment is not a detail here: the item row sat 4px high and that alone
    took Blade of the Ruined King from 0.805 to 0.121, failing the confidence
    gate on a frame whose art is near-identical to the catalogue. Correcting
    the constants recovered most of it, but the residual still moves a pixel
    between frames, and a pixel is worth ~0.07 of score.

    Cheap by construction: find the slot that already matches best at the
    nominal offset, then slide only THAT slot against only its own winning
    template. One template over a 7x7 window, not the whole catalogue, and
    the answer applies to every slot in the row because the offset is a
    property of the popup rather than the slot.
    """
    bank = templates().get(kind) or {}
    if not bank:
        return 0, 0
    y0, size, x0, pitch, count = GEOMETRY[kind]
    h, w = int(size * fy), int(size * fx)
    weights = _weights(True, kind == "runes")

    def tile_at(i: int, dy: int, dx: int) -> np.ndarray:
        ty, tx = int(y0 * fy) + dy, int((x0 + i * pitch) * fx) + dx
        if ty < 0 or tx < 0:
            return np.empty(0)
        return image[ty:ty + h, tx:tx + w]

    anchor: tuple[float, np.ndarray | None, int] = (0.0, None, 0)
    for i in range(count):
        tile = tile_at(i, 0, 0)
        if tile.size == 0:
            continue
        norm = _norm_tile(tile)
        score, name = max((_score(norm, weights, t), n) for n, t in bank.items())
        if score > anchor[0]:
            anchor = (score, bank[name], i)
    if anchor[1] is None:
        return 0, 0

    best_score, best = anchor[0], (0, 0)
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            tile = tile_at(anchor[2], dy, dx)
            if tile.size == 0:
                continue
            score = _score(_norm_tile(tile), weights, anchor[1])
            if score > best_score:
                best_score, best = score, (dy, dx)
    return best


def read_build_icons(image: np.ndarray) -> dict:
    """Identify every spell, rune and item in a build popup.

    Returns {"spells": [...], "runes": [...], "items": [...],
             "_confidence": {row: [(name, score, gap), ...]}}.
    Unreadable slots are "?" -- an empty item slot scores near zero and is
    dropped from the item list entirely.
    """
    h, w = image.shape[:2]
    fy, fx = h / 1080.0, w / 2340.0
    out: dict = {"_confidence": {}}
    for kind, (y0, size, x0, pitch, count) in GEOMETRY.items():
        names, conf = [], []
        dy, dx = _align(image, kind, fy, fx)
        for i in range(count):
            ty, tx = int(y0 * fy) + dy, int((x0 + i * pitch) * fx) + dx
            tile = image[ty:ty + int(size * fy), tx:tx + int(size * fx)]
            name, score, gap, _ = match_slot(tile, kind)
            names.append(name)
            conf.append((name, round(score, 3), round(gap, 3)))
        if kind == "items":                       # trailing empty slots
            while names and names[-1] == "?" and conf[-1][1] < MIN_SCORE:
                names.pop(); conf.pop()
        out[kind] = names
        out["_confidence"][kind] = conf
    return out


# ---------------------------------------------------------------------------
# Champion portraits on the leaderboard
# ---------------------------------------------------------------------------
# The 2026-09-25 relayout removed the champion NAME text from the CHAMPION tab
# entirely: rows carry a portrait, that champion's rank-1 player and a score,
# and the bottom-left name label on screen 2 is gone. OCR has nothing left to
# read, so identity comes from the portrait, which is the same problem this
# module already solves for build popups.
#
# Portraits are drawn as CIRCLES inside a gold ring, exactly like runes, so
# they take the circular window for the same reason: a square comparison
# scores the ring instead of the face.

CHAMPION_DIR = "champions"
#: (portrait_x, first_row_y, pitch, size, count) at 2340x1080.
# Refined by the same dy,dx search _align uses, then folded back into the
# constants. It matters as much here as it does for items: at the nominal
# (599, 284) the Graves row scored 0.411 with a 0.054 gap and read as an
# honest "?", while four pixels left it scores 0.939 with a 0.635 gap.
# Runtime alignment rescued it either way, but starting from the right place
# leaves the search correcting sub-pixel drift rather than a real error.
CHAMPION_GEOMETRY = {
    # screen 1, overview: champion portrait at the left of each row
    "overview": (593, 282, 158, 90, 5),
    # screen 2, detail: the persistent champion switcher column
    "switcher": (595, 282, 158, 90, 5),
}
#: Portraits are far more self-similar than items (many champions share
#: armour, skin tone and background), so the gate is looser than MIN_GAP but
#: still refuses a coin flip. Measured on the 2026-09-25 captures: correct
#: matches scored 0.46-0.83 while the two ambiguous rows sat at gaps of
#: 0.03-0.06, which is what these thresholds are set to exclude.
CHAMP_MIN_SCORE = 0.30
CHAMP_MIN_GAP = 0.08


@functools.lru_cache(maxsize=1)
def champion_templates() -> dict[str, np.ndarray]:
    """{canonical champion name: normalised template} from the shipped art."""
    from . import champions as champ_module

    # Match on a key with every separator stripped, not a hyphenated slug.
    # The shipped filenames drop apostrophes outright (kaisa, khazix, chogath,
    # ksante, kogmaw, velkoz) while a hyphenating slug produces kai-sa and
    # friends, so seven real Wild Rift champions silently had no template and
    # could never be identified. Nunu additionally carries an HTML-escaped
    # ampersand in the filename (nunu-amp-willump), hence the & -> amp variant.
    by_key: dict[str, str] = {}
    for name in champ_module.CHAMPIONS:
        low = name.lower()
        for variant in (low, low.replace("&", " amp ")):
            by_key.setdefault(re.sub(r"[^a-z0-9]", "", variant), name)
    out: dict[str, np.ndarray] = {}
    folder = PUBLIC / CHAMPION_DIR
    if not folder.is_dir():
        return out
    for f in folder.iterdir():
        if f.suffix.lower() not in (".png", ".webp", ".jpg", ".jpeg"):
            continue
        name = by_key.get(re.sub(r"[^a-z0-9]", "", f.stem.lower()))
        if name is None:
            continue
        art = _load_art(f"{CHAMPION_DIR}/{f.name}")
        if art is not None:
            out[name] = _norm_tile(art)

    # Champion OVERLAY bank: portraits harvested from captured frames, for
    # champions the shipped art cannot identify. Same idea as the item bank
    # and for the same reason -- the catalogue head icon is drawn at a
    # different zoom and framing from the circular switcher portrait, and for
    # most champions that is close enough while for a few it is not.
    #
    # Cho'Gath and Hwei both shipped with PC League art and both failed on the
    # GAP rather than the score: 0.434 with the right answer as runner-up
    # 0.020 behind, and 0.505 at 0.013. Replacing the catalogue file outright
    # was the wrong fix -- that file is also what the website renders, and a
    # ringed in-game portrait next to 140 clean head icons looks broken. The
    # bank keeps the two uses separate.
    bank = ROOT / "data" / "icon_bank" / "champions.npz"
    if bank.exists():
        with np.load(bank) as z:
            for key in z.files:
                if key in by_key.values() or key in champ_module.CHAMPIONS:
                    out[key] = z[key].astype(np.float32)
    return out


def match_champion(tile: np.ndarray) -> tuple[str, float, float, str]:
    """(name_or_?, score, gap, runner_up) for one cropped portrait."""
    cands = champion_templates()
    if not cands or tile.size == 0:
        return "?", 0.0, 0.0, ""
    t = _norm_tile(tile)
    w = _weights(False, True)          # circular, no badge overlay on portraits
    ranked = sorted(((_score(t, w, tpl), n) for n, tpl in cands.items()),
                    reverse=True)
    (s1, n1), (s2, n2) = ranked[0], ranked[1] if len(ranked) > 1 else (0.0, "")
    gap = s1 - s2
    ok = s1 >= CHAMP_MIN_SCORE and gap >= CHAMP_MIN_GAP
    return (n1 if ok else "?"), s1, gap, n2


def _align_champions(image, layout: str, fy: float, fx: float) -> tuple[int, int]:
    """Return the portrait column's real offset from its nominal geometry.

    The champion list is not fixed to one y origin.  While the list settles
    (and after a partial scroll) the same five rows have been observed 10-28
    pixels above the calibrated grid.  The old +/-4 template search then
    cropped two portraits together: Rengar became unreadable and Wukong could
    look more like Warwick.  That is the worst failure mode because it is a
    confident wrong champion rather than an honest miss.

    Detect the gold portrait circles first.  Their centres are dramatically
    easier and cheaper to locate than searching every champion template over
    a wide area, and the median offset rejects a stray circle.  Keep the old
    small template refinement as a fallback for unusual frames where Hough
    cannot see enough rings.
    """
    bank = champion_templates()
    if not bank:
        return 0, 0
    x0, y0, pitch, size, count = CHAMPION_GEOMETRY[layout]
    h, w = int(size * fy), int(size * fx)
    weights = _weights(False, True)

    # Hough's answer, or the nominal grid when it cannot see enough rings.
    seed_dy, seed_dx = 0, 0

    # Search only the narrow champion-switcher band, so player avatars and
    # rank emblems elsewhere on the screen cannot join the circle set.
    band_half = int(115 * fx)
    band_left = max(0, int(x0 * fx) - band_half)
    band_right = min(image.shape[1], int(x0 * fx) + band_half)
    band = image[:, band_left:band_right]
    if band.size:
        gray = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 1.2)
        scale = min(fx, fy)
        circles = cv2.HoughCircles(
            gray,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=max(20, int(100 * fy)),
            param1=100,
            param2=32,
            minRadius=max(8, int(35 * scale)),
            maxRadius=max(12, int(56 * scale)),
        )
        if circles is not None:
            offsets: list[tuple[int, int, int]] = []
            used_rows: set[int] = set()
            for cx, cy, _radius in sorted(circles[0], key=lambda c: c[1]):
                absolute_x = int(round(cx)) + band_left
                absolute_y = int(round(cy))
                # Scrolling is allowed to move a row by almost half a pitch,
                # but never far enough to make it the neighbouring slot.
                nearest = int(round((absolute_y / fy - y0) / pitch))
                if not 0 <= nearest < count or nearest in used_rows:
                    continue
                expected_y = int((y0 + nearest * pitch) * fy)
                dy = absolute_y - expected_y
                if abs(dy) > int(pitch * fy * 0.48):
                    continue
                used_rows.add(nearest)
                offsets.append((dy, absolute_x - int(x0 * fx), nearest))
            if len(offsets) >= 3:
                dys = sorted(v[0] for v in offsets)
                dxs = sorted(v[1] for v in offsets)
                # SEED the template search rather than returning. A ring
                # centre is only accurate to a pixel or two, and this column
                # does not tolerate that: on a settled capture Hough answered
                # (-1, -2) where the true offset was (0, 0), and Graves fell
                # from 0.939 to 0.655 -- still the right champion, but a
                # margin that thin is what the confidence gate exists to
                # refuse. Hough finds the row; the template finds the pixel.
                seed_dy = dys[len(dys) // 2]
                seed_dx = dxs[len(dxs) // 2]

    def tile_at(i: int, dy: int, dx: int):
        ty = int((y0 + i * pitch - size / 2) * fy) + dy
        tx = int((x0 - size / 2) * fx) + dx
        if ty < 0 or tx < 0:
            return np.empty(0)
        return image[ty:ty + h, tx:tx + w]

    anchor = (0.0, None, 0)
    for i in range(count):
        tile = tile_at(i, seed_dy, seed_dx)
        if tile.size == 0:
            continue
        norm = _norm_tile(tile)
        score, name = max((_score(norm, weights, t), n) for n, t in bank.items())
        if score > anchor[0]:
            anchor = (score, bank[name], i)
    if anchor[1] is None:
        return 0, 0
    best_score, best = anchor[0], (seed_dy, seed_dx)
    for dy in range(seed_dy - 4, seed_dy + 5):
        for dx in range(seed_dx - 4, seed_dx + 5):
            tile = tile_at(anchor[2], dy, dx)
            if tile.size == 0:
                continue
            s = _score(_norm_tile(tile), weights, anchor[1])
            if s > best_score:
                best_score, best = s, (dy, dx)
    return best


def read_champion_portraits(image: np.ndarray,
                            layout: str = "switcher") -> list[dict]:
    """Identify the champion in each visible row.

    Returns [{"y": row_centre_y, "champion": name_or_None, "score", "gap"}]
    top to bottom. An unresolved row is champion=None rather than a guess,
    which is the whole point: the caller can re-read or skip instead of
    navigating to the wrong champion.
    """
    h, w = image.shape[:2]
    fy, fx = h / 1080.0, w / 2340.0
    x0, y0, pitch, size, count = CHAMPION_GEOMETRY[layout]
    dy, dx = _align_champions(image, layout, fy, fx)
    rows = []
    for i in range(count):
        cy = y0 + i * pitch
        ty = int((cy - size / 2) * fy) + dy
        tx = int((x0 - size / 2) * fx) + dx
        tile = image[ty:ty + int(size * fy), tx:tx + int(size * fx)]
        name, score, gap, runner = match_champion(tile)
        rows.append({"y": int(cy * fy) + dy, "champion": None if name == "?" else name,
                     "score": round(score, 3), "gap": round(gap, 3),
                     "runnerUp": runner})
    return rows


#: The switcher box's left edge, native x. Sampled wide enough that a couple
#: of pixels of capture drift cannot miss a border only a few pixels thick.
SELECTION_EDGE_X = (438, 472)
#: With the fade-invariant test below, a selected row reads 0.053-0.070 and
#: every unselected row reads exactly 0.000 across every capture we have. The
#: only non-zero noise is the build popup, which covers the switcher and peaks
#: at 0.0038, so this sits ~5x above the noise and ~2.7x below the weakest
#: real selection.
#:
#: It used to be 0.004, which separated a real selection from the build popup
#: by 0.0002. That margin was never real.
SELECTION_MIN_GOLD = 0.02


def selected_champion_row(image: np.ndarray) -> int | None:
    """Index of the highlighted switcher row, or None if nothing is selected.

    None is meaningful rather than a failure: the OVERVIEW state has no
    selection at all, so this doubles as the state test.
    """
    h, w = image.shape[:2]
    fy, fx = h / 1080.0, w / 2340.0
    _x0, y0, pitch, _size, count = CHAMPION_GEOMETRY["switcher"]
    dy, _dx = _align_champions(image, "switcher", fy, fx)
    a = image.astype(np.float32)
    x_lo, x_hi = int(SELECTION_EDGE_X[0] * fx), int(SELECTION_EDGE_X[1] * fx)
    best = (0.0, None)
    for i in range(count):
        cy = int((y0 + i * pitch) * fy) + dy
        strip = a[max(0, cy - int(70 * fy)):cy + int(70 * fy), x_lo:x_hi]
        if strip.size == 0:
            continue
        b, g, r = strip[:, :, 0], strip[:, :, 1], strip[:, :, 2]
        # Gold is RED OVER BLUE, not "blue is low". The absolute ceiling this
        # used to carry (b < 110) is the one clause a screen transition
        # breaks: the game fades the whole screen toward white between
        # champions, every channel rises together, and the border stops
        # qualifying while still being plainly gold on screen. Measured on two
        # frames from the 2026-10-05 run, the selected row scored 0.0029 and
        # 0.0032 against a 0.0040 threshold -- correctly the only gold-bearing
        # row of the five, and rejected anyway. The carousel read that as "the
        # tap did not select", backed out, and skipped the champion.
        #
        # The relative clause is untouched by the fade (0.07 faded against
        # 0.06 clean) because adding white to a colour moves r and b together.
        # Dropping the ceiling takes the selected row from 0.003 to 0.069 on
        # those frames while every unselected row stays at exactly 0.000.
        gold = float(((r > 140) & (g > 110) & (r > b + 60)).mean())
        if gold > best[0]:
            best = (gold, i)
    return best[1] if best[0] >= SELECTION_MIN_GOLD else None


def read_selected_champion(image: np.ndarray) -> str | None:
    """The champion the detail view is currently showing, or None.

    Replaces read_champion_name() against SCREEN_2_CHAMP_LABEL_REGION, which
    the 2026-09-25 relayout deleted from the UI.
    """
    i = selected_champion_row(image)
    if i is None:
        return None
    rows = read_champion_portraits(image, "switcher")
    return rows[i]["champion"] if i < len(rows) else None


def scan_champion_rows_by_portrait(
    image: np.ndarray, layout: str = "overview"
) -> list[tuple[int, str | None]]:
    """[(row_centre_y, champion_or_None)], the same shape scan_champion_rows
    returned, so callers that navigated by name keep working unchanged."""
    return [(r["y"], r["champion"])
            for r in read_champion_portraits(image, layout)]


def leaderboard_state(image: np.ndarray) -> str | None:
    """"overview", "detail", or None if this is not a champion leaderboard.

    Replaces the old "did any champion NAME OCR?" page test. A frame counts
    only when at least three rows resolve to real champions: two would let a
    pair of lucky matches on an unrelated screen pass, and every genuine
    capture resolved five of five.
    """
    rows = read_champion_portraits(image, "switcher")
    if sum(1 for r in rows if r["champion"]) < 3:
        return None
    return "detail" if selected_champion_row(image) is not None else "overview"
