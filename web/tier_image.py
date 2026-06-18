"""Render the tier list as a shareable PNG — modern, minimal, clean.

Design goals:
  - flat dark background, no glossy tier badges or visual gimmicks
  - generous padding so champion names and win-rate % never clip
  - subtitle calls out the methodology ("EU - Top 50 players per champion")
  - tiers wrap their champions onto multiple rows when there are many, so
    nothing is silently truncated
  - rendered at 2x then downscaled for crisp antialiasing
"""
from __future__ import annotations

import io
from pathlib import Path

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from web.champion_assets import icon_url


# Tier colour (single fill — flat, no gradient gloss).
_TIER_COLOR: dict[str, tuple[int, int, int]] = {
    "GOD": (255, 94, 58),    # vivid coral-red
    "S":   (255, 140, 66),   # orange
    "A":   (255, 200, 61),   # gold
    "B":   (74, 144, 255),   # accent blue
    "C":   (107, 116, 139),  # slate
    "Ass": (58, 64, 85),     # muted deep slate
}
_TIER_TEXT: dict[str, tuple[int, int, int]] = {
    "GOD": (255, 255, 255),
    "S":   (255, 255, 255),
    "A":   (44, 24, 0),       # dark on gold for contrast
    "B":   (255, 255, 255),
    "C":   (255, 255, 255),
    "Ass": (174, 180, 198),
}
_TIER_ORDER = ["GOD", "S", "A", "B", "C", "Ass"]

# Palette
_BG = (8, 12, 26)
_CARD = (16, 22, 40)
_BORDER = (32, 40, 64)
_TEXT = (236, 240, 252)
_MUTED = (140, 150, 176)
_ACCENT = (90, 160, 255)
_GRID_LINE = (255, 255, 255, 16)

# Layout — 2x supersampled, downscaled on save for crisp output.
_S = 2
_W = 1280 * _S
_PAD = 40 * _S
_HEADER_H = 260 * _S
_FOOTER_H = 110 * _S
_RADIUS = 16 * _S

_TIER_LABEL_W = 200 * _S
_GAP_LABEL_STRIP = 16 * _S
_STRIP_PAD = 26 * _S

# Champion item dimensions inside the strip
_ICON_SIZE = 100 * _S
_ITEM_W = _ICON_SIZE + 48 * _S        # room for a short name centred under the icon
_ITEM_GAP_X = 18 * _S
_NAME_GAP = 14 * _S
_NAME_H = 36 * _S
_WR_GAP = 4 * _S
_WR_H = 30 * _S
_ITEM_H = _ICON_SIZE + _NAME_GAP + _NAME_H + _WR_GAP + _WR_H

_TIER_LABEL_HEIGHT = _ITEM_H + 2 * _STRIP_PAD   # row height matches a single-row strip
_LOGO_HEIGHT = 130 * _S


# ----- font helpers ----------------------------------------------------

def _candidate_font_paths(bold: bool) -> list[Path]:
    if bold:
        names = [
            "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        names = [
            "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    return [Path(p) for p in names if Path(p).exists()]


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    for path in _candidate_font_paths(bold):
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


# ----- asset loaders ---------------------------------------------------

@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _fetch_icon_bytes(name: str) -> bytes | None:
    try:
        r = requests.get(icon_url(name), timeout=5)
        r.raise_for_status()
        return r.content
    except (requests.RequestException, ValueError):
        return None


def _load_icon(name: str, size: int) -> Image.Image | None:
    url = icon_url(name)
    try:
        if url.startswith("/app/static/"):
            rel = url[len("/app/static/"):]
            path = Path(__file__).resolve().parent.parent / "static" / rel
            if not path.exists():
                return None
            img = Image.open(path).convert("RGBA")
        else:
            raw = _fetch_icon_bytes(name)
            if raw is None:
                return None
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
        return img.resize((size, size), Image.LANCZOS)
    except Exception:
        return None


def _load_logo(height: int) -> Image.Image | None:
    path = Path(__file__).resolve().parent.parent / "static" / "logo.png"
    if not path.exists():
        return None
    try:
        logo = Image.open(path).convert("RGBA")
        scale = height / logo.height
        return logo.resize((int(logo.width * scale), height), Image.LANCZOS)
    except Exception:
        return None


# ----- drawing helpers -------------------------------------------------

def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    return mask


def _text_centered(draw, xy, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((xy[0] - w / 2 - bbox[0], xy[1] - h / 2 - bbox[1]),
              text, font=font, fill=fill)


def _truncate_to_fit(draw, text: str, font: ImageFont.ImageFont, max_w: int) -> str:
    """Add an ellipsis if `text` would render wider than `max_w`."""
    if draw.textbbox((0, 0), text, font=font)[2] <= max_w:
        return text
    ell = "…"
    while text and draw.textbbox((0, 0), text + ell, font=font)[2] > max_w:
        text = text[:-1]
    return (text + ell) if text else ell


# ----- main render -----------------------------------------------------

def render_tier_list_png(
    buckets: dict[str, list[tuple]],
    subtitle: str = "",
) -> bytes:
    """Render a modern minimal tier list to a PNG (bytes).

    `buckets` is {tier_label: [(champion_name, weighted_wr, [is_otp, [is_hard]]),
    ...]}. The optional flags decorate the champion icon:
      * `is_otp=True`  → small orange "OTP" badge top-right
      * `is_hard=True` → red ring around the icon for Hard / Very Hard champs

    Old 2-tuple calls still work. Tiers with many champions wrap onto extra
    rows so nothing is hidden.
    """
    # Normalise: ensure every champion entry is (name, wr, is_otp, is_hard).
    buckets = {
        t: [(
            c[0], c[1],
            (c[2] if len(c) > 2 else False),
            (c[3] if len(c) > 3 else False),
        ) for c in cs]
        for t, cs in buckets.items()
    }
    tiers = _TIER_ORDER

    # Plan each tier's row height up front so we know the total canvas size.
    strip_w = _W - 2 * _PAD - _TIER_LABEL_W - _GAP_LABEL_STRIP
    inner_w = strip_w - 2 * _STRIP_PAD
    cols = max(1, (inner_w + _ITEM_GAP_X) // (_ITEM_W + _ITEM_GAP_X))

    tier_heights: dict[str, int] = {}
    for t in tiers:
        n = len(buckets.get(t, []))
        rows = max(1, -(-n // cols)) if n > 0 else 1  # ceil-div, min 1
        strip_h = 2 * _STRIP_PAD + rows * _ITEM_H + (rows - 1) * (_ITEM_GAP_X)
        tier_heights[t] = max(_TIER_LABEL_HEIGHT, strip_h)

    total_h = _HEADER_H + sum(tier_heights.values()) + (len(tiers) - 1) * (10 * _S) + _FOOTER_H

    img = Image.new("RGB", (_W, total_h), color=_BG)
    draw = ImageDraw.Draw(img, "RGBA")

    # ---- Header ----
    logo = _load_logo(_LOGO_HEIGHT)
    title_x = _PAD
    if logo is not None:
        img.paste(logo, (_PAD, (_HEADER_H - _LOGO_HEIGHT) // 2), logo)
        title_x = _PAD + logo.width + 26 * _S

    title_font = _font(96 * _S, bold=True)
    sub_font = _font(34 * _S, bold=False)
    sub_font_sm = _font(30 * _S, bold=True)
    title_y = _HEADER_H // 2 - 76 * _S
    draw.text((title_x, title_y), "Champion Tier List", font=title_font, fill=_TEXT)
    # Methodology — ALWAYS visible so anyone screenshotting the tier list
    # knows where the numbers come from.
    methodology = "Winrates are based on top 50 players average per champion"
    draw.text((title_x, title_y + 102 * _S), methodology,
              font=sub_font, fill=_MUTED)
    # Filter / context line (e.g. "Filter: Jungle") — only when provided.
    if subtitle:
        draw.text((title_x, title_y + 146 * _S), subtitle,
                  font=sub_font_sm, fill=_ACCENT)

    # Right-aligned URL
    url_font = _font(38 * _S, bold=True)
    url_text = "wrtruemeta.com"
    ub = draw.textbbox((0, 0), url_text, font=url_font)
    draw.text((_W - _PAD - (ub[2] - ub[0]), _HEADER_H // 2 - 19 * _S),
              url_text, font=url_font, fill=_ACCENT)

    # Hairline under the header
    draw.line((_PAD, _HEADER_H - 1, _W - _PAD, _HEADER_H - 1),
              fill=_BORDER, width=1)

    # ---- Tier rows ----
    label_font = _font(120 * _S, bold=True)
    label_font_sm = _font(86 * _S, bold=True)
    name_font = _font(30 * _S, bold=True)
    wr_font = _font(26 * _S, bold=False)
    empty_font = _font(34 * _S, bold=False)
    circle_mask = _circle_mask(_ICON_SIZE)

    y = _HEADER_H + 10 * _S
    for t in tiers:
        row_h = tier_heights[t]
        # Tier label (flat colour block, no gloss)
        lx0, ly0 = _PAD, y
        lx1, ly1 = _PAD + _TIER_LABEL_W, y + row_h
        col = _TIER_COLOR[t]
        draw.rounded_rectangle((lx0, ly0, lx1, ly1), radius=_RADIUS, fill=col)
        # Very subtle inner highlight at top — adds depth without going glossy
        draw.line((lx0 + _RADIUS, ly0 + 1, lx1 - _RADIUS, ly0 + 1),
                  fill=(255, 255, 255, 50), width=1)
        lfont = label_font if len(t) <= 1 else label_font_sm
        _text_centered(draw, ((lx0 + lx1) / 2, (ly0 + ly1) / 2),
                       t, lfont, _TIER_TEXT[t])

        # Strip card (champion area)
        sx0 = lx0 + _TIER_LABEL_W + _GAP_LABEL_STRIP
        sx1 = _W - _PAD
        draw.rounded_rectangle((sx0, ly0, sx1, ly1), radius=_RADIUS,
                               fill=_CARD, outline=_BORDER, width=1)

        champs = buckets.get(t, [])
        if not champs:
            _text_centered(draw, ((sx0 + sx1) / 2, (ly0 + ly1) / 2),
                           "No champions in this tier",
                           empty_font, _MUTED)
            y += row_h + 10 * _S
            continue

        # Layout icons left-to-right, wrapping to additional rows as needed.
        usable_w = (sx1 - _STRIP_PAD) - (sx0 + _STRIP_PAD)
        cols_now = max(1, (usable_w + _ITEM_GAP_X) // (_ITEM_W + _ITEM_GAP_X))
        # Centre the cluster if there are fewer items than columns available.
        items_in_first_row = min(len(champs), cols_now)
        row_width = items_in_first_row * _ITEM_W + (items_in_first_row - 1) * _ITEM_GAP_X
        # When a tier has more items than cols, left-align; otherwise centre.
        if len(champs) > cols_now:
            start_x = sx0 + _STRIP_PAD
        else:
            start_x = sx0 + (sx1 - sx0 - row_width) // 2

        otp_badge_font = _font(20 * _S, bold=True)
        for i, (name, wr, is_otp, is_hard) in enumerate(champs):
            col_idx = i % cols_now
            row_idx = i // cols_now
            ix = start_x + col_idx * (_ITEM_W + _ITEM_GAP_X)
            iy = ly0 + _STRIP_PAD + row_idx * (_ITEM_H + _ITEM_GAP_X)

            icon_x = ix + (_ITEM_W - _ICON_SIZE) // 2
            icon_y = iy

            icon = _load_icon(name, _ICON_SIZE)
            if icon is not None:
                img.paste(icon, (icon_x, icon_y), circle_mask)
                # Red ring for Hard / Very Hard champions, otherwise hairline.
                if is_hard:
                    for w in range(3 * _S):
                        draw.ellipse(
                            (icon_x - w, icon_y - w,
                             icon_x + _ICON_SIZE + w, icon_y + _ICON_SIZE + w),
                            outline=(255, 90, 90), width=1,
                        )
                else:
                    draw.ellipse((icon_x, icon_y, icon_x + _ICON_SIZE,
                                  icon_y + _ICON_SIZE),
                                 outline=(255, 255, 255, 40), width=1)
            else:
                draw.ellipse((icon_x, icon_y, icon_x + _ICON_SIZE,
                              icon_y + _ICON_SIZE),
                             fill=(40, 50, 80))
                _text_centered(draw,
                               (icon_x + _ICON_SIZE / 2, icon_y + _ICON_SIZE / 2),
                               name[:1].upper(), name_font, _TEXT)

            # OTP badge in the top-right of the icon for one-trick-pony champs.
            if is_otp:
                bw, bh = 26 * _S, 14 * _S
                bx0 = icon_x + _ICON_SIZE - bw + 4 * _S
                by0 = icon_y - 3 * _S
                draw.rounded_rectangle(
                    (bx0, by0, bx0 + bw, by0 + bh),
                    radius=4 * _S,
                    fill=(255, 140, 66),
                    outline=(0, 0, 0, 180),
                    width=1,
                )
                _text_centered(draw, (bx0 + bw / 2, by0 + bh / 2),
                               "OTP", otp_badge_font, (255, 255, 255))

            # Champion name (truncated to item width) + WR underneath.
            name_disp = _truncate_to_fit(draw, name, name_font, _ITEM_W - 4 * _S)
            cx = ix + _ITEM_W // 2
            _text_centered(draw, (cx, icon_y + _ICON_SIZE + _NAME_GAP + _NAME_H // 2),
                           name_disp, name_font, _TEXT)
            _text_centered(draw, (cx, icon_y + _ICON_SIZE + _NAME_GAP + _NAME_H + _WR_GAP + _WR_H // 2),
                           f"{wr:.1f}%", wr_font, _ACCENT)

        y += row_h + 10 * _S

    # ---- Footer ----
    fy = total_h - _FOOTER_H
    draw.line((_PAD, fy, _W - _PAD, fy), fill=_BORDER, width=1)
    foot_font = _font(38 * _S, bold=True)
    draw.text((_PAD, fy + 25 * _S), "wrtruemeta.com",
              font=foot_font, fill=_ACCENT)
    foot_sub = _font(28 * _S, bold=False)
    note = "Wild Rift Meta Tracker  ·  Updated twice a month"
    fb = draw.textbbox((0, 0), note, font=foot_sub)
    draw.text((_W - _PAD - (fb[2] - fb[0]), fy + 30 * _S),
              note, font=foot_sub, fill=_MUTED)

    # Downscale for antialiasing crispness.
    final = img.resize((_W // _S, total_h // _S), Image.LANCZOS)
    buf = io.BytesIO()
    final.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
