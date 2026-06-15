"""Render a single-champion stat card as a shareable PNG.

Used by the Leaderboard page's "Share card" feature — a compact image a user
can download and drop into Discord / WhatsApp / etc. Pure PIL.
"""
from __future__ import annotations

import io
from pathlib import Path

import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from web.champion_assets import icon_url, splash_url


_W, _H = 880, 440          # card size (2x-ish for crispness)
_BG_TOP = (12, 16, 32)
_BG_BOT = (7, 10, 22)
_TEXT = (233, 238, 255)
_MUTED = (140, 150, 176)
_ACCENT = (74, 144, 255)
_GOLD = (255, 225, 136)

_TIER_COLORS = {
    "GOD": (229, 90, 30), "S": (255, 107, 26), "A": (245, 184, 0),
    "B": (43, 106, 214), "C": (90, 99, 120), "Ass": (74, 80, 102),
    "?": (90, 99, 120),
}


def _font(size: int, bold: bool = True) -> ImageFont.ImageFont:
    names = (
        ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold else
        ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for p in names:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        return r.content
    except (requests.RequestException, ValueError):
        return None


def _load(url: str) -> Image.Image | None:
    if url.startswith("/app/static/"):
        p = Path(__file__).resolve().parent.parent / "static" / url[len("/app/static/"):]
        if not p.exists():
            return None
        try:
            return Image.open(p).convert("RGBA")
        except Exception:
            return None
    raw = _fetch(url)
    if raw is None:
        return None
    try:
        return Image.open(io.BytesIO(raw)).convert("RGBA")
    except Exception:
        return None


def _vgrad(w, h, top, bot):
    g = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        g.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    return g.resize((w, h))


def _logo(height: int) -> Image.Image | None:
    p = Path(__file__).resolve().parent.parent / "static" / "logo.png"
    if not p.exists():
        return None
    try:
        lg = Image.open(p).convert("RGBA")
        s = height / lg.height
        return lg.resize((int(lg.width * s), height), Image.LANCZOS)
    except Exception:
        return None


def render_champion_card(
    *, champion: str, tier: str, win_rate: float | None, ceiling_wr: float | None,
    median_games: float | None, best_player: str | None, best_player_wr: float | None,
    champ_class: str, role: str,
) -> bytes:
    """Render a shareable champion stat card PNG and return the bytes."""
    img = _vgrad(_W, _H, _BG_TOP, _BG_BOT).convert("RGBA")

    # Splash art on the right, faded into the card.
    splash = _load(splash_url(champion))
    if splash is not None:
        # cover-fit into right ~55% of the card
        target_w = int(_W * 0.58)
        ratio = max(target_w / splash.width, _H / splash.height)
        sp = splash.resize((int(splash.width * ratio), int(splash.height * ratio)), Image.LANCZOS)
        sp = sp.crop((0, 0, target_w, _H))
        # left-edge alpha fade so it blends into the text side
        fade = Image.new("L", sp.size, 255)
        fd = fade.load()
        fade_px = int(target_w * 0.5)
        for x in range(target_w):
            if x < fade_px:
                for y in range(_H):
                    fd[x, y] = int(255 * (x / fade_px))
        sp.putalpha(fade)
        img.alpha_composite(sp, (_W - target_w, 0))

    # Darken overlay on the left for text legibility.
    ov = Image.new("RGBA", (_W, _H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rectangle((0, 0, int(_W * 0.55), _H), fill=(7, 10, 22, 180))
    img = Image.alpha_composite(img, ov.filter(ImageFilter.GaussianBlur(30)))

    draw = ImageDraw.Draw(img, "RGBA")
    pad = 36

    # Logo top-left
    lg = _logo(40)
    if lg is not None:
        img.alpha_composite(lg, (pad, pad - 6))

    # Champion icon + name
    icon = _load(icon_url(champion))
    iy = pad + 54
    if icon is not None:
        ic = icon.resize((84, 84), Image.LANCZOS)
        mask = Image.new("L", (84, 84), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 83, 83), fill=255)
        img.paste(ic, (pad, iy), mask)
        draw.ellipse((pad, iy, pad + 84, iy + 84), outline=_ACCENT, width=3)

    name_x = pad + 102
    draw.text((name_x, iy + 6), champion, font=_font(40), fill=_TEXT)
    draw.text((name_x, iy + 52), f"{role}  ·  {champ_class}", font=_font(18, False), fill=_MUTED)

    # Tier badge (top-right of text area)
    tcol = _TIER_COLORS.get(tier, (90, 99, 120))
    tb_w, tb_h = 92, 64
    tb_x = int(_W * 0.55) - tb_w - 24
    draw.rounded_rectangle((tb_x, pad, tb_x + tb_w, pad + tb_h), radius=12, fill=tcol)
    tf = _font(34) if len(tier) <= 1 else _font(26)
    tbb = draw.textbbox((0, 0), tier, font=tf)
    draw.text((tb_x + (tb_w - (tbb[2] - tbb[0])) / 2, pad + (tb_h - (tbb[3] - tbb[1])) / 2 - tbb[1]),
              tier, font=tf, fill=(255, 255, 255))

    # Stat blocks
    def stat(x, y, label, value, color=_TEXT):
        draw.text((x, y), label.upper(), font=_font(13, False), fill=_MUTED)
        draw.text((x, y + 18), value, font=_font(28), fill=color)

    sy = iy + 120
    col_w = 150
    stat(pad, sy, "Win Rate", f"{win_rate:.1f}%" if win_rate is not None else "—", _ACCENT)
    stat(pad + col_w, sy, "Ceiling", f"{ceiling_wr:.1f}%" if ceiling_wr is not None else "—")
    stat(pad + col_w * 2, sy, "Median Games",
         f"{int(round(median_games)):,}" if median_games is not None else "—")

    sy2 = sy + 70
    bp = best_player or "—"
    if len(bp) > 18:
        bp = bp[:17] + "…"
    draw.text((pad, sy2), "BEST PLAYER", font=_font(13, False), fill=_MUTED)
    draw.text((pad, sy2 + 18), bp, font=_font(24), fill=_GOLD)
    if best_player_wr is not None:
        draw.text((pad, sy2 + 50), f"{best_player_wr:.1f}% confidence-adjusted",
                  font=_font(14, False), fill=_MUTED)

    # Footer
    draw.text((pad, _H - 30), "wrtruemeta.com  ·  Top 50 players  ·  updated twice a month",
              font=_font(14, False), fill=_MUTED)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
