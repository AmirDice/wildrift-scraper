"""Reusable HTML rendering helpers for the WRTrueMeta app.

These build markup that pairs with the CSS in `web/style.py`, so we can drop
Streamlit's default `st.dataframe` (which never matched the page design) in
favour of clean themed tables and cells.
"""
from __future__ import annotations

import math
import statistics
from html import escape
from typing import Callable

from web.champion_assets import icon_url
from web.champion_meta import difficulty_dots, difficulty_label


# ----- notice pills ----------------------------------------------------

_NOTICE_KINDS = {
    "accent": ("rgba(74,144,255,0.1)", "rgba(74,144,255,0.3)", "var(--accent)"),
    "gold":   ("rgba(212,166,74,0.1)", "rgba(212,166,74,0.3)", "var(--gold)"),
}


def site_footer() -> str:
    """Universal page footer — contact + Riot disclaimer. Call from every
    Streamlit page so the contact line is consistent everywhere."""
    return (
        '<div style="color:var(--muted);font-size:0.82rem;text-align:center;'
        'margin-top:3rem;padding-top:1.25rem;border-top:1px solid rgba(255,255,255,0.06);'
        'line-height:1.7;">'
        'Questions or feedback? DM <strong style="color:var(--accent);">@generalthr4gg</strong> on Discord.<br/>'
        'Not affiliated with Riot Games. League of Legends &amp; Wild Rift are '
        '&copy; Riot Games, Inc.'
        '</div>'
    )


def notice_pill(text: str, icon: str = "&#x21bb;", kind: str = "accent") -> str:
    """A small rounded info pill. `icon` is raw HTML (entity or char)."""
    bg, border, color = _NOTICE_KINDS.get(kind, _NOTICE_KINDS["accent"])
    return (
        f'<span style="display:inline-flex;align-items:center;gap:0.5rem;'
        f'background:{bg};border:1px solid {border};border-radius:999px;'
        f'padding:0.35rem 0.9rem;color:{color};font-size:0.82rem;font-weight:600;">'
        f'<span style="font-size:0.9rem;line-height:1;">{icon}</span>{text}</span>'
    )


def notice_bar(pills: list[str]) -> str:
    """Wrap a list of `notice_pill` outputs into a flex row."""
    return (
        '<div style="display:flex;flex-wrap:wrap;gap:0.6rem;margin-bottom:1.25rem;">'
        + "".join(pills)
        + "</div>"
    )


# Shared "why are all win rates above 50%?" explainer used on every page
# that surfaces win rates.
TOP50_NOTICE = notice_pill(
    "Top-50 win rates &mdash; all above 50%, since elite mains win more than "
    "average. A low number means weaker at high level, not a losing champion. "
    "If you&rsquo;re a top player and below a champion&rsquo;s listed win rate, "
    "you&rsquo;re underperforming on it.",
    icon="&#9432;", kind="gold",
)
UPDATED_NOTICE = notice_pill(
    "Win rates are updated twice a month", icon="&#x21bb;", kind="accent",
)

# Helps visitors read the (intentionally tight) win-rate gaps. The "1 pt =
# 1 extra win per 100 games" framing turns an abstract gap into something
# players can feel; the "2 pts = one tier" mapping anchors the tier list
# numerically.
GAP_NOTICE = notice_pill(
    "Each percentage point &asymp; one extra win per 100 games. "
    "2 pts = one tier; 4+ pts = clearly stronger at high level.",
    icon="&#9776;", kind="accent",
)

# Forward-looking feature teases (used as small pills until the real things ship)
NA_WINRATES_NOTICE = notice_pill(
    "NA win rates &mdash; coming soon", icon="&#127482;&#127480;", kind="gold",
)
BEST_BUILDS_NOTICE = notice_pill(
    "Best-player builds &mdash; coming soon", icon="&#9874;", kind="accent",
)


# ----- cell builders ---------------------------------------------------

def champ_cell(name: str) -> str:
    """Champion icon + name."""
    safe = escape(str(name))
    return (
        f'<div class="cell-champ"><img src="{icon_url(name)}" alt="{safe}" />'
        f'<span class="cn">{safe}</span></div>'
    )


def tier_pill(label: str, css_class: str) -> str:
    return f'<span class="tier-pill {css_class}">{escape(label)}</span>'


def class_chip(champ_class: str) -> str:
    safe = escape(str(champ_class))
    return f'<span class="class-chip {safe}">{safe}</span>'


def difficulty_cell(d: int) -> str:
    """Five dots (each = 2 points of the 1-10 scale) + word label."""
    word = difficulty_label(d)
    bucket = {"Easy": "easy", "Moderate": "moderate",
              "Hard": "hard", "Very Hard": "veryhard"}.get(word, "moderate")
    filled = difficulty_dots(d)
    dots = "".join(
        f'<span class="diff-dot {"on " + bucket if i < filled else ""}"></span>'
        for i in range(5)
    )
    return f'<span class="diff-dots">{dots}<span class="diff-label">{word}</span></span>'


# ----- table -----------------------------------------------------------

class Col:
    """A table column.

    label   : header text
    render  : fn(row_dict) -> html string for the cell
    align   : "left" | "num" | "center"
    """
    def __init__(self, label: str, render: Callable[[dict], str], align: str = "left"):
        self.label = label
        self.render = render
        self.align = align


def consistency_label(winrates: list[float]) -> tuple[str, float]:
    """Map the spread of a champion's top-player win rates to a label.

    Returns (label, stdev). Lower stdev = the champion performs consistently
    across its top players (anyone good wins on it); higher stdev = results
    swing on the individual player.
    """
    vals = [float(w) for w in winrates if w is not None]
    if len(vals) < 2:
        return ("—", 0.0)
    sd = statistics.pstdev(vals)
    if sd < 6:
        return ("Very consistent", sd)
    if sd < 9:
        return ("Consistent", sd)
    if sd < 12:
        return ("Variable", sd)
    return ("Volatile", sd)


def winrate_distribution_svg(winrates: list[float], *, width: int = 460,
                             height: int = 160) -> str:
    """Inline SVG of the win-rate DISTRIBUTION as a smooth bell-ish curve.

    Uses a small Gaussian KDE so the curve peaks where the top players' win
    rates cluster. A tall narrow peak = consistent (everyone good wins about
    the same); a wide low spread = volatile (results swing on the player).
    The x-axis is win rate; a dashed gold line marks the average.
    """
    vals = [float(w) for w in winrates if w is not None]
    if len(vals) < 2:
        return '<div style="color:var(--muted);font-size:0.85rem;">Not enough data.</div>'

    pad_l, pad_r, pad_t, pad_b = 14, 14, 14, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # X range: pad around the data, clamped to sane WR bounds.
    lo = max(30, min(vals) - 5)
    hi = min(95, max(vals) + 5)
    span = (hi - lo) or 1.0
    mean_v = statistics.fmean(vals)
    sd = statistics.pstdev(vals) or 2.0
    bw = max(1.5, sd * 0.6)  # KDE bandwidth

    n = 96
    xs = [lo + span * i / (n - 1) for i in range(n)]
    norm = 1.0 / (len(vals) * bw * math.sqrt(2 * math.pi))

    def density(x: float) -> float:
        return norm * sum(math.exp(-0.5 * ((x - v) / bw) ** 2) for v in vals)

    dens = [density(x) for x in xs]
    dmax = max(dens) or 1.0

    def px(x: float) -> float:
        return pad_l + (x - lo) / span * plot_w

    def py(d: float) -> float:
        return pad_t + (1 - d / dmax) * plot_h

    pts = [(px(x), py(d)) for x, d in zip(xs, dens)]
    base_y = pad_t + plot_h
    line_path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area_path = (
        f"M{pts[0][0]:.1f},{base_y:.1f} "
        + "L" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        + f" L{pts[-1][0]:.1f},{base_y:.1f} Z"
    )

    # X-axis ticks (lo, mid, hi)
    ticks = ""
    for v in (lo, (lo + hi) / 2, hi):
        x = px(v)
        ticks += (
            f'<line x1="{x:.1f}" y1="{base_y}" x2="{x:.1f}" y2="{base_y + 4}" '
            f'stroke="rgba(255,255,255,0.2)" stroke-width="1"/>'
            f'<text x="{x:.1f}" y="{height - 6}" fill="#8a92a8" font-size="10" '
            f'font-family="sans-serif" text-anchor="middle">{v:.0f}%</text>'
        )
    baseline = (f'<line x1="{pad_l}" y1="{base_y}" x2="{width - pad_r}" y2="{base_y}" '
                f'stroke="rgba(255,255,255,0.1)" stroke-width="1"/>')
    mean_x = px(mean_v)
    mean_line = (
        f'<line x1="{mean_x:.1f}" y1="{pad_t}" x2="{mean_x:.1f}" y2="{base_y}" '
        f'stroke="#ffd14a" stroke-width="1.5" stroke-dasharray="4,3"/>'
        f'<text x="{mean_x:.1f}" y="{pad_t - 2}" fill="#ffd14a" font-size="10" '
        f'font-family="sans-serif" text-anchor="middle">avg {mean_v:.1f}%</text>'
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" '
        f'preserveAspectRatio="xMidYMid meet" style="display:block;overflow:visible;">'
        '<defs><linearGradient id="wrarea" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="rgba(74,144,255,0.4)"/>'
        '<stop offset="100%" stop-color="rgba(74,144,255,0.02)"/>'
        '</linearGradient></defs>'
        f'{baseline}'
        f'<path d="{area_path}" fill="url(#wrarea)"/>'
        f'<path d="{line_path}" fill="none" stroke="#5fa0ff" stroke-width="2.5" '
        'stroke-linejoin="round" stroke-linecap="round"/>'
        f'{mean_line}{ticks}</svg>'
    )


def render_table(columns: list[Col], rows: list[dict], *, highlight_top: int = 3,
                 scroll: bool = False) -> str:
    """Return an HTML string for a themed table.

    `rows` is a list of dicts; each Col.render receives the whole row dict.
    The first `highlight_top` rows get gold/silver/bronze row tinting.
    When `scroll` is True the body is capped to ~5 visible rows with a pinned
    header and a styled scrollbar.
    """
    head = "".join(
        f'<th class="{c.align if c.align != "left" else ""}">{escape(c.label)}</th>'
        for c in columns
    )
    body = ""
    for i, row in enumerate(rows):
        rcls = f"r-top{i + 1}" if i < highlight_top else ""
        tds = "".join(
            f'<td class="{c.align if c.align != "left" else ""}">{c.render(row)}</td>'
            for c in columns
        )
        body += f'<tr class="{rcls}">{tds}</tr>'
    wrap_cls = "wr-table-wrap wr-table-scroll" if scroll else "wr-table-wrap"
    # The hint div appears only on mobile (CSS-controlled) and tells users
    # they can swipe horizontally. Sits outside .wr-table-wrap so it doesn't
    # scroll with the table content.
    return (
        '<div class="wr-table-outer">'
        '<div class="wr-table-hint" aria-hidden="true">'
        '<span>&larr; swipe to see all columns &rarr;</span>'
        '</div>'
        f'<div class="{wrap_cls}"><table class="wr-table">'
        f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody>'
        '</table></div>'
        '</div>'
    )
