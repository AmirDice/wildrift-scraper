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
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "web-next" / "public"

#: slot geometry inside a 2340x1080 popup: (y0, size, x0, pitch, count)
GEOMETRY = {
    "spells": (283, 90, 1246, 110, 2),
    "runes": (470, 92, 1248, 101, 5),
    "items": (642, 88, 1246, 104, 6),
}

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
    """(name_or_?, score, gap, runner_up) for one cropped slot."""
    cands = templates()[kind]
    if not cands or tile.size == 0:
        return "?", 0.0, 0.0, ""
    t = _norm_tile(tile)
    w = _weights(True, kind == "runes")
    ranked = sorted(((_score(t, w, tpl), name) for name, tpl in cands.items()), reverse=True)
    (s1, n1), (s2, n2) = ranked[0], ranked[1] if len(ranked) > 1 else (0.0, "")
    gap = s1 - s2
    ok = s1 >= MIN_SCORE and gap >= MIN_GAP
    return (n1 if ok else "?"), s1, gap, n2


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
        for i in range(count):
            ty, tx = int(y0 * fy), int((x0 + i * pitch) * fx)
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
