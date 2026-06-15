"""WRTrueMeta - landing page.

Run with:
    streamlit run streamlit_app.py
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from web.champion_assets import icon_url, splash_url
from web.champion_meta import champion_class, champion_difficulty, difficulty_label
from web.champion_roles import ROLES, roles_for
from web.components import consistency_label, site_footer, tier_pill, winrate_distribution_svg
from web.data_loader import (
    assign_tier,
    best_player_per_champion,
    champion_summary,
    funny_names,
    get_champions,
    load_leaderboard,
    meta_breakdown,
    meta_role_strength,
    multi_champion_mains,
    off_meta_picks,
    pick_of_the_patch,
    role_avg_winrate,
    skill_spread,
    winrate_by_difficulty,
)
from web.local_assets import ashen_samira, landing_bg, season_bg
from web.style import inject_css, top_nav


st.set_page_config(
    page_title="WRTrueMeta - Wild Rift Meta Tracker",
    page_icon=":crossed_swords:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

# Load early so the nav and hero search can populate the champion datalist.
df = load_leaderboard()
ALL_CHAMPIONS = get_champions(df) if not df.empty else []

# --- Landing-only page background ---------------------------------------
# The Spirit Blossom art fills the TOP of the page (not in a card), fading
# to solid dark navy by the time the user reaches the season-in-progress
# section. Pixel-stop gradient keeps the cutoff at a predictable distance
# from the top regardless of how tall the rest of the page gets.
st.markdown(
    f"""
    <style>
    .stApp {{
        background:
            linear-gradient(180deg,
                rgba(7,11,24,0.35) 0px,
                rgba(7,11,24,0.55) 220px,
                rgba(7,11,24,0.88) 460px,
                var(--bg) 600px),
            url('{landing_bg()}') no-repeat top center,
            var(--bg);
        background-size: auto, 100% auto, auto;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)
top_nav(active="Home", champions=ALL_CHAMPIONS)


# --- Hero (no search bar — search lives in the nav; the space below is
# --- used for the four at-a-glance stat widgets instead) -----------------
st.markdown(
    """
    <div class="hero" style="padding-bottom: 0.5rem;">
      <h1>Wild Rift <span class="accent">Meta</span> Tracker</h1>
      <p>
        The official <span class="pill">EU</span> top champion win rates &mdash;
        built from the <span class="pill">top 50</span> players of every champion.
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)


# Small forward-feature pill so visitors know more is coming.
from web.components import NA_WINRATES_NOTICE as _NA_NOTICE, notice_bar as _nb
st.markdown(_nb([_NA_NOTICE]), unsafe_allow_html=True)


# --- Four at-a-glance stat widgets --------------------------------------
def _stat_widget(eyebrow: str, big: str, value: str, descriptor: str, *,
                 icon: str | None = None, big_class: str = "",
                 value_class: str = "") -> str:
    """A stat widget: label + big name (+ icon) on the left, a large win-rate
    number filling the right side."""
    icon_html = (f'<img class="sw-icon" src="{icon}" alt="" />' if icon else "")
    return (
        f'<div class="stat-widget">'
        f'  <div class="sw-left">'
        f'    <div class="sw-eyebrow">{eyebrow}</div>'
        f'    <div class="sw-main">{icon_html}<span class="sw-big {big_class}">{big}</span></div>'
        f'    <div class="sw-sub">{descriptor}</div>'
        f'  </div>'
        f'  <div class="sw-right"><div class="sw-pct {value_class}">{value}</div></div>'
        f'</div>'
    )


if not df.empty:
    _summary = champion_summary(df)
    _meta = meta_breakdown(df)
    _credible = [m for m in _meta if m["n_champions"] >= 5]
    _meta_head = _credible[0] if _credible else (_meta[0] if _meta else None)
    _potp = pick_of_the_patch(df)
    # Strongest meta role = highest WR among each role's TOP 10 meta picks.
    # Better signal than role_avg_winrate for "which role is hottest right
    # now" because it ignores the off-meta tail nobody picks at high elo.
    _meta_roles = meta_role_strength(df, top_n_per_role=10)
    _best_role = None
    for _r, _st in sorted(
        ((r, s) for r, s in _meta_roles.items()
         if s is not None and not s["low_confidence"]),
        key=lambda kv: kv[1]["wr"], reverse=True,
    ):
        _best_role = (_r, _st)
        break
    _worst = _summary[_summary["weighted_winrate"].notna()].iloc[-1] if not _summary.empty else None

    widgets = []
    if _meta_head:
        widgets.append(_stat_widget(
            "Current Meta", f'{_meta_head["champ_class"]}', f'{_meta_head["wr"]:.1f}%',
            "avg win rate", big_class="accent"))
    if _potp:
        widgets.append(_stat_widget(
            "Top Meta Champion", _potp["champion"], f'{_potp["weighted_winrate"]:.1f}%',
            "win rate", icon=icon_url(_potp["champion"])))
    if _best_role:
        widgets.append(_stat_widget(
            "Strongest Meta Role", _best_role[0], f'{_best_role[1]["wr"]:.1f}%',
            "top 10 picks avg"))
    if _worst is not None:
        widgets.append(_stat_widget(
            "Worst Champion", str(_worst["champion"]), f'{_worst["weighted_winrate"]:.1f}%',
            "win rate", icon=icon_url(str(_worst["champion"])), value_class="down"))

    if widgets:
        st.markdown(
            f'<div class="stat-widgets">{"".join(widgets)}</div>',
            unsafe_allow_html=True,
        )


# --- Featured champion spotlight ---------------------------------------
# Edit `SPOTLIGHT_CHAMPION` to feature a different champion. The widget
# silently disables itself if that champion isn't in the scraped data.
SPOTLIGHT_CHAMPION = "Hecarim"

if not df.empty:
    _sl_row = champion_summary(df)
    _sl_row = _sl_row[_sl_row["champion"] == SPOTLIGHT_CHAMPION]
    if not _sl_row.empty:
        r = _sl_row.iloc[0]
        tier_label, tier_class = assign_tier(r["weighted_winrate"])

        # Best player (Wilson) on this champion
        _best_df = best_player_per_champion(df[df["champion"] == SPOTLIGHT_CHAMPION])
        _best = _best_df[_best_df["is_best_for_champ"]]
        best_html = ""
        if not _best.empty:
            b = _best.iloc[0]
            best_html = (
                f'<div class="spotlight-bestplayer">'
                f'<span class="muted">Best player:</span> '
                f'<strong>{b["player_name"]}</strong> '
                f'<span class="muted">&middot; rank #{int(b["rank"])} '
                f'&middot; {float(b["confidence_wr"]):.1f}% adjusted</span>'
                f'</div>'
            )

        role = roles_for(SPOTLIGHT_CHAMPION)[0]
        cls = champion_class(SPOTLIGHT_CHAMPION)
        diff = champion_difficulty(SPOTLIGHT_CHAMPION)

        # Consistency chart: distribution of the top-50 players' raw win rates
        _sl_wrs = (
            df[df["champion"] == SPOTLIGHT_CHAMPION]["winrate"]
            .dropna().astype(float).tolist()
        )
        sl_label, sl_sd = consistency_label(_sl_wrs)
        sl_dist_svg = winrate_distribution_svg(_sl_wrs, width=620, height=140)
        chart_card_html = (
            '<div class="sl-chart-card">'
            '  <div class="sl-chart-head">'
            '    <div class="sl-chart-title">Win-Rate Distribution</div>'
            f'    <div class="sl-chart-meta"><span class="accent">{sl_label}</span>'
            f'{"" if sl_sd == 0 else f" &nbsp;&middot;&nbsp; &sigma; = {sl_sd:.1f} pts"}</div>'
            '  </div>'
            f'  {sl_dist_svg}'
            '</div>'
        )

        st.markdown(
            f"""
            <div class="spotlight-card">
              <div class="spotlight-card-bg" style="background-image: url('{splash_url(SPOTLIGHT_CHAMPION)}');"></div>
              <div class="spotlight-card-overlay"></div>
              <div class="spotlight-content">
                <div>
                  <div class="spotlight-eyebrow">Featured Champion &middot; {tier_label} tier</div>
                  <div class="spotlight-headline">
                    <div class="spotlight-name">{SPOTLIGHT_CHAMPION}</div>
                    <div class="spotlight-tags">
                      {role} <span class="sep">&middot;</span>
                      {cls} <span class="sep">&middot;</span>
                      {difficulty_label(diff)}
                    </div>
                  </div>
                </div>
                <div class="spotlight-stats">
                  <div class="sl-stat">
                    <div class="sl-stat-label">Tier</div>
                    <div class="sl-stat-value {tier_class}">{tier_label}</div>
                  </div>
                  <div class="sl-stat">
                    <div class="sl-stat-label">Win Rate</div>
                    <div class="sl-stat-value accent">{r["weighted_winrate"]:.1f}%</div>
                  </div>
                  <div class="sl-stat">
                    <div class="sl-stat-label">Ceiling WR</div>
                    <div class="sl-stat-value gold">{r["max_winrate"]:.1f}%</div>
                  </div>
                  <div class="sl-stat">
                    <div class="sl-stat-label">Median Games</div>
                    <div class="sl-stat-value">{int(round(r["median_games"])):,}</div>
                  </div>
                </div>
                {chart_card_html}
                {best_html}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


# --- Season in progress -------------------------------------------------
# Update these two dates each time Riot kicks off a new patch / season.
# Everything else (days left, % complete, end-date label) is derived from
# them automatically, so the card now reads correctly on every page load.
SEASON_NUM = 21
SEASON_TITLE = "FLAT OUT PATCH"
SEASON_START = date(2026, 4, 22)   # first day of S21
SEASON_END   = date(2026, 7, 9)    # last day of S21

_today = date.today()
_total_days = max(1, (SEASON_END - SEASON_START).days)
_elapsed = max(0, min(_total_days, (_today - SEASON_START).days))
DAYS_LEFT = max(0, (SEASON_END - _today).days)
COMPLETE_PCT = round(_elapsed / _total_days * 100)
# Manual month + day + year join — Windows' strftime doesn't support `%-d`
# (no leading-zero day-of-month), and "%d" would give us "Jul 09, 2026"
# which looks wrong. Stitching the day in by hand sidesteps both issues.
ENDS_AT = f"{SEASON_END.strftime('%b')} {SEASON_END.day}, {SEASON_END.year}"

FEATURED_NEW_CHAMPION = "Skarner"
FEATURED_NEW_CHAMPION_TITLE = "The Vanguard of the Ancients"
FEATURED_NEW_SKIN_NAME = "ASHEN KNIGHT SAMIRA"
FEATURED_NEW_SKIN_SUB = "Legendary"

# Kai'Sa background lives in its own layer (.season-card-bg) so it can drift
# with a slow Ken-Burns animation while the gradient overlay + text stay put.
_kaisa_bg_style = f"background-image: url('{season_bg()}');"

st.markdown(
    f"""
    <div class="season-card">
      <div class="season-card-bg" style="{_kaisa_bg_style}"></div>
      <div class="season-card-overlay"></div>
      <div>
        <div><span class="season-dot"></span><span class="season-label">Season in Progress</span></div>
        <div class="season-row">
          <div class="season-emblem">&#9670;</div>
          <div>
            <div style="display:flex;gap:1.25rem;align-items:baseline;">
              <div class="season-number">S{SEASON_NUM}</div>
              <div>
                <div class="season-tag">SEASON {SEASON_NUM}</div>
                <div class="season-title">{SEASON_TITLE}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width:{COMPLETE_PCT}%"></div></div>
        <div class="season-meta">
          <strong>{DAYS_LEFT}</strong> days left &nbsp;·&nbsp; ends {ENDS_AT} &nbsp;·&nbsp;
          <strong>{COMPLETE_PCT}%</strong> complete
        </div>
      </div>
      <div style="display:flex;flex-direction:column;gap:0.65rem;">
        <div class="season-feature">
          <span class="feature-tag">NEW CHAMPION</span>
          <div style="flex:1;min-width:0;">
            <div class="feature-name">{FEATURED_NEW_CHAMPION.upper()}</div>
            <div class="feature-sub">{FEATURED_NEW_CHAMPION_TITLE}</div>
          </div>
          <div class="feature-avatar"><img src="{icon_url(FEATURED_NEW_CHAMPION)}" alt="{FEATURED_NEW_CHAMPION}" /></div>
        </div>
        <div class="season-feature">
          <span class="feature-tag green">NEW SKIN</span>
          <div style="flex:1;min-width:0;">
            <div class="feature-name">{FEATURED_NEW_SKIN_NAME}</div>
            <div class="feature-sub">{FEATURED_NEW_SKIN_SUB}</div>
          </div>
          <div class="feature-avatar"><img src="{ashen_samira()}" alt="{FEATURED_NEW_SKIN_NAME}" /></div>
        </div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# --- Two-column preview: Top Meta Champions  |  Top of the Leaderboard ----
col_left, col_right = st.columns(2)


def _avatar_html(label: str, klass: str = "", *, img_src: str | None = None, alt: str = "") -> str:
    """Render an avatar circle. If `img_src` is provided we drop an <img>
    inside (DDragon icon); otherwise we just show the text label."""
    if img_src:
        return f'<div class="avatar {klass}"><img src="{img_src}" alt="{alt or label}" /></div>'
    return f'<div class="avatar {klass}">{label}</div>'


def _rank_class(i: int) -> str:
    """CSS class for the rank cell — gradient gold/silver/bronze for top 3."""
    return {1: "r-1", 2: "r-2", 3: "r-3"}.get(i, "")


def _ring_class(i: int) -> str:
    """Avatar ring for the top 3."""
    return {1: "ring-gold", 2: "ring-silver", 3: "ring-bronze"}.get(i, "")


summary = champion_summary(df)

with col_left:
    rows = []
    seen = set()
    for _, r in summary.head(3).iterrows():
        rows.append((r["champion"], r["weighted_winrate"]))
        seen.add(r["champion"])
    placeholders = [
        ("Hecarim", 54.3), ("Amumu", 52.6), ("Rammus", 51.8),
        ("Taliyah", 51.2), ("Gragas", 50.9),
    ]
    for name, wr in placeholders:
        if len(rows) >= 3: break
        if name in seen: continue
        rows.append((name, wr))
        seen.add(name)

    rank_rows = ""
    for i, (name, wr) in enumerate(rows[:3], start=1):
        wr_text = f"{wr:.1f}% WR" if pd.notna(wr) else "—"
        t_label, t_class = assign_tier(wr)
        is_new = name.lower() == "taliyah"
        badge = '<span class="badge">NEW</span>' if is_new else ""
        avatar = _avatar_html(name[0].upper(), klass=_ring_class(i), img_src=icon_url(name), alt=name)
        rank_rows += (
            f'<div class="row r-top">'
            f'  <div class="rank {_rank_class(i)}">{i}</div>'
            f'  {avatar}'
            f'  <div class="name">{name}{badge}</div>'
            f'  <div class="wr">{wr_text}</div>'
            f'  <div class="pick">{tier_pill(t_label, t_class)}</div>'
            f'</div>'
        )
    st.markdown(
        f"""
        <div class="wr-card">
          <div class="wr-card-header">
            <div class="wr-card-title">Top Meta Champions</div>
            <a class="wr-card-link" href="Tier_List" target="_self">View Tier List &rarr;</a>
          </div>
          <div class="row-list">{rank_rows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


with col_right:
    rank_rows = ""
    if df.empty:
        rank_rows = (
            '<div style="color:var(--muted);padding:1rem 0;">'
            'No leaderboard data yet. Run '
            '<code style="color:var(--accent);">python -m src.scrape_timed --target Aatrox --n 200</code> '
            'to populate.</div>'
        )
    else:
        top3 = df.sort_values("score", ascending=False).head(3)
        for i, (_, row) in enumerate(top3.iterrows(), start=1):
            name = str(row["player_name"] or "—")
            champ = str(row["champion"])
            score = f"{int(row['score']):,}" if pd.notna(row["score"]) else "—"
            avatar = _avatar_html(champ[:1], klass=_ring_class(i), img_src=icon_url(champ), alt=champ)
            rank_rows += (
                f'<div class="row r-top">'
                f'  <div class="rank {_rank_class(i)}">#{i}</div>'
                f'  {avatar}'
                f'  <div class="name">{name}</div>'
                f'  <div class="score">{score}</div>'
                f'  <div></div>'
                f'</div>'
            )
    st.markdown(
        f"""
        <div class="wr-card">
          <div class="wr-card-header">
            <div class="wr-card-title">Top of the Leaderboard</div>
            <a class="wr-card-link" href="Leaderboard" target="_self">View Leaderboards &rarr;</a>
          </div>
          <div class="row-list">{rank_rows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- INSIGHT SECTIONS ------------------------------------------------------

def _insight_card(title: str, df_subset: pd.DataFrame,
                  metric_col: str, metric_fmt, *,
                  metric_class: str = "",
                  show_top: int = 3, show_more_up_to: int = 15) -> str:
    """Render an insight card showing top N rows with one metric, plus a
    "View more" <details> revealing rows N+1 through `show_more_up_to`."""

    def row_html(i: int, r) -> str:
        champ = str(r["champion"])
        val = r[metric_col]
        val_str = metric_fmt(val) if pd.notna(val) else "—"
        rk_cls = {1: "r-1", 2: "r-2", 3: "r-3"}.get(i, "")
        return (
            f'<div class="insight-row">'
            f'  <div class="rank {rk_cls}">#{i}</div>'
            f'  <div class="icon"><img src="{icon_url(champ)}" alt="{champ}" /></div>'
            f'  <div class="name">{champ}</div>'
            f'  <div class="metric {metric_class}">{val_str}</div>'
            f'</div>'
        )

    top_rows = "".join(
        row_html(i, r) for i, (_, r) in
        enumerate(df_subset.head(show_top).iterrows(), start=1)
    )
    if not top_rows:
        return (
            '<div class="insight-card">'
            f'  <div class="insight-card-title">{title}</div>'
            '  <div style="color:var(--muted);font-size:0.9rem;padding:0.5rem 0;">No data yet.</div>'
            '</div>'
        )

    extra = df_subset.iloc[show_top:show_more_up_to]
    if len(extra) == 0:
        more_html = ""
    else:
        extra_rows = "".join(
            row_html(i, r) for i, (_, r) in
            enumerate(extra.iterrows(), start=show_top + 1)
        )
        more_html = (
            '<details class="insight-more">'
            f'  <summary>View more &middot; {len(extra)} more</summary>'
            f'  <div class="insight-extra">{extra_rows}</div>'
            '</details>'
        )

    return (
        '<div class="insight-card">'
        f'  <div class="insight-card-title">{title}</div>'
        f'  {top_rows}{more_html}'
        '</div>'
    )


if not df.empty:
    # --- Role strength card ------------------------------------------
    # Show BOTH metrics so players can read what they care about:
    #   - Meta WR (top 10 picks per role) — what the high-elo meta is doing
    #   - Pool WR (all tracked champs) — overall role health
    _meta_role_wrs = meta_role_strength(df, top_n_per_role=10)
    _pool_role_wrs = role_avg_winrate(df)
    role_cells = ""
    for role in ROLES:
        meta_stat = _meta_role_wrs.get(role)
        pool_stat = _pool_role_wrs.get(role)
        if meta_stat is None and pool_stat is None:
            role_cells += (
                f'<div class="role-wr-cell">'
                f'  <div class="role-name">{role}</div>'
                f'  <div class="role-wr empty">no data</div>'
                f'</div>'
            )
            continue
        meta_wr_txt = f'{meta_stat["wr"]:.1f}%' if meta_stat else "—"
        pool_wr_txt = f'{pool_stat["wr"]:.1f}%' if pool_stat else "—"
        n_champs = pool_stat["n_champions"] if pool_stat else 0
        low_conf = (meta_stat and meta_stat["low_confidence"]) or (pool_stat and pool_stat["low_confidence"])
        wr_class = "role-wr low-conf" if low_conf else "role-wr"
        flag = ' <span class="role-flag" title="Limited data — few champions scraped in this role">&#9888;</span>' if low_conf else ""
        role_cells += (
            f'<div class="role-wr-cell">'
            f'  <div class="role-name">{role}</div>'
            f'  <div class="{wr_class}">{meta_wr_txt}{flag}</div>'
            f'  <div class="role-sub">'
            f'    <span class="role-sub-label">Meta picks</span>'
            f'  </div>'
            f'  <div class="role-pool">'
            f'    <span class="role-pool-wr">{pool_wr_txt}</span>'
            f'    <span class="role-pool-label">whole pool &middot; {n_champs} champ{"s" if n_champs != 1 else ""}</span>'
            f'  </div>'
            f'</div>'
        )
    st.markdown(
        f"""
        <div class="wr-card" style="margin: 1.5rem 0;">
          <div class="wr-card-header">
            <div class="wr-card-title">Role Strength</div>
            <div style="color:var(--muted);font-size:0.78rem;">Top 10 meta picks (big) &middot; all tracked champions (small)</div>
          </div>
          <div class="role-wr-grid">{role_cells}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Highest / Lowest WR / Off-meta picks row ---------------------
    fmt_pct = lambda v: f"{v:.1f}%"
    fmt_int = lambda v: f"{int(round(v)):,}"

    top_wr   = summary.sort_values("weighted_winrate", ascending=False)
    bot_wr   = summary[summary["weighted_winrate"].notna()].sort_values("weighted_winrate", ascending=True)
    off_meta = off_meta_picks(df)

    st.markdown(
        f"""
        <div class="insights-grid">
          {_insight_card("Highest Win Rate", top_wr, "weighted_winrate", fmt_pct, metric_class="")}
          {_insight_card("Lowest Win Rate",  bot_wr, "weighted_winrate", fmt_pct, metric_class="down")}
          {_insight_card("Strong Off-Meta",  off_meta, "weighted_winrate", fmt_pct, metric_class="gold")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Most/Least played + funniest names row -----------------------
    most_played  = summary.sort_values("total_games", ascending=False)
    least_played = summary[summary["total_games"] > 0].sort_values("total_games", ascending=True)

    # Funniest names card (distinct format — player names, not champions).
    # No rank / WR column; just icon + name, with a "View more" expander.
    funny = funny_names(df, limit=18)

    def _funny_row(f) -> str:
        return (
            f'<div class="insight-row">'
            f'  <div class="icon"><img src="{icon_url(f["champion"])}" alt="{f["champion"]}" /></div>'
            f'  <div class="name">{f["player_name"]}</div>'
            f'</div>'
        )

    top_funny = "".join(_funny_row(f) for f in funny[:3])
    extra_funny = funny[3:]
    if extra_funny:
        funny_more = (
            '<details class="insight-more">'
            f'  <summary>View more &middot; {len(extra_funny)} more</summary>'
            f'  <div class="insight-extra">{"".join(_funny_row(f) for f in extra_funny)}</div>'
            '</details>'
        )
    else:
        funny_more = ""
    if not top_funny:
        top_funny = '<div style="color:var(--muted);font-size:0.9rem;padding:0.5rem 0;">No standout names yet.</div>'
    funny_card = (
        '<div class="insight-card funny">'
        '  <div class="insight-card-title">Funniest Names <span class="accent">&#128514;</span></div>'
        f'  {top_funny}{funny_more}'
        '</div>'
    )

    st.markdown(
        f"""
        <div class="insights-grid">
          {_insight_card("Most Played",    most_played,  "total_games",  fmt_int, metric_class="muted")}
          {_insight_card("Least Played",   least_played, "total_games",  fmt_int, metric_class="muted")}
          {funny_card}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Beginner-friendly / Best OTP champs / Most contested ---------
    # Easy-to-play yet effective: low difficulty (<=4) sorted by win rate.
    beginners = summary[summary["difficulty"] <= 4].sort_values(
        "weighted_winrate", ascending=False)
    # Best OTP champs: among OTP-flagged champions (algorithmic + community
    # known), the highest-WR picks. Answers "if I want to one-trick, which
    # OTP champion is strongest right now?"
    best_otp = summary[summary["is_otp"]].sort_values(
        "weighted_winrate", ascending=False)
    # Deepest talent pools: highest median mastery = most contested / popular.
    contested = summary[summary["median_mastery"].notna()].sort_values(
        "median_mastery", ascending=False)

    st.markdown(
        f"""
        <div class="insights-grid">
          {_insight_card("Best for Beginners", beginners, "weighted_winrate", fmt_pct, metric_class="")}
          {_insight_card("Best OTP Champs",    best_otp,  "weighted_winrate", fmt_pct, metric_class="gold")}
          {_insight_card("Most Contested",     contested, "median_mastery", lambda v: f"{int(round(v)):,}", metric_class="muted")}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Skill expression / Most consistent / Multi-champion mains ---
    spread = skill_spread(df, summary)
    spread = spread[spread["n_players"] >= 20]  # cut tiny pools
    consistent = summary[
        summary["winrate_std"].notna() & (summary["n_players"] >= 20)
    ].sort_values("winrate_std", ascending=True)

    # Multi-champion mains: top-50 on 3+ champions = genuinely-elite mechanics.
    mains = multi_champion_mains(df, min_champions=3)

    def _mains_row(m: dict) -> str:
        first_champ = m["champions"][0] if m["champions"] else None
        icon_html = (
            f'<div class="icon"><img src="{icon_url(first_champ)}" alt="{first_champ}" /></div>'
            if first_champ else '<div class="icon"></div>'
        )
        wr = f"{m['avg_winrate']:.0f}%" if m["avg_winrate"] is not None else "—"
        return (
            f'<div class="insight-row">'
            f'  {icon_html}'
            f'  <div class="name">{m["player_name"]}'
            f'    <div style="color:var(--muted);font-size:0.7rem;font-weight:500;">'
            f'      {m["n_champions"]} champs &middot; best #{m["best_rank"]}</div>'
            f'  </div>'
            f'  <div class="metric muted">{wr}</div>'
            f'</div>'
        )

    top_mains = "".join(_mains_row(m) for m in mains[:3])
    extra_mains = mains[3:18]
    if extra_mains:
        mains_more = (
            '<details class="insight-more">'
            f'  <summary>View more &middot; {len(extra_mains)} more</summary>'
            f'  <div class="insight-extra">{"".join(_mains_row(m) for m in extra_mains)}</div>'
            '</details>'
        )
    else:
        mains_more = ""
    if not top_mains:
        top_mains = '<div style="color:var(--muted);font-size:0.9rem;padding:0.5rem 0;">Not enough overlap yet.</div>'
    mains_card = (
        '<div class="insight-card">'
        '  <div class="insight-card-title">Multi-Champion Mains</div>'
        f'  {top_mains}{mains_more}'
        '</div>'
    )

    st.markdown(
        f"""
        <div class="insights-grid">
          {_insight_card("Skill Expression", spread,     "skill_spread", lambda v: f"{v:.1f} pts", metric_class="gold")}
          {_insight_card("Most Consistent",  consistent, "winrate_std",  lambda v: f"&plusmn;{v:.1f}", metric_class="muted")}
          {mains_card}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Current meta breakdown (win rate by champion class) ----------
    meta = meta_breakdown(df)
    # Headline meta = highest-WR class with a credible champion count.
    CLASS_MIN = 5
    credible = [m for m in meta if m["n_champions"] >= CLASS_MIN]
    headline = credible[0] if credible else (meta[0] if meta else None)
    if meta:
        max_wr = max(m["wr"] for m in meta)
        min_wr = min(m["wr"] for m in meta)
        span = (max_wr - min_wr) or 1.0
        bars = ""
        for m in meta:
            pct = (m["wr"] - min_wr) / span * 100
            is_head = headline is not None and m["champ_class"] == headline["champ_class"]
            bar_cls = "meta-bar-fill head" if is_head else "meta-bar-fill"
            low = ' <span class="meta-flag" title="Few champions scraped in this class">&#9888;</span>' if m["n_champions"] < CLASS_MIN else ""
            bars += (
                f'<div class="meta-row">'
                f'  <div class="meta-class">{m["champ_class"]}{low}</div>'
                f'  <div class="meta-bar"><div class="{bar_cls}" style="width:{max(8, pct):.0f}%"></div></div>'
                f'  <div class="meta-wr">{m["wr"]:.1f}%</div>'
                f'  <div class="meta-n">{m["n_champions"]} champs</div>'
                f'</div>'
            )
        headline_txt = (
            f'It&rsquo;s a <span class="accent">{headline["champ_class"]}</span> meta right now'
            if headline else "Meta breakdown"
        )
        st.markdown(
            f"""
            <div class="wr-card" style="margin: 1.5rem 0;">
              <div class="wr-card-header">
                <div class="wr-card-title">Current Meta &mdash; {headline_txt}</div>
                <div style="color:var(--muted);font-size:0.78rem;">Games-weighted win rate by champion class</div>
              </div>
              <div class="meta-grid">{bars}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # --- Win rate by difficulty bucket ---------------------------------
    diff_rows = winrate_by_difficulty(summary)
    if diff_rows:
        d_max = max(d["wr"] for d in diff_rows)
        d_min = min(d["wr"] for d in diff_rows)
        d_span = (d_max - d_min) or 1.0
        # Headline answers the keyword query "are hard champions worth it".
        delta_pts = d_max - d_min
        if delta_pts < 1.0:
            d_headline = (
                'Difficulty barely matters &mdash; '
                '<span class="accent">every bucket wins within ~1 point</span>'
            )
        else:
            top = max(diff_rows, key=lambda d: d["wr"])
            d_headline = (
                f'<span class="accent">{top["difficulty"]}</span> champions win most '
                f'({delta_pts:.1f}pt gap between top and bottom buckets)'
            )
        d_bars = ""
        for d in diff_rows:
            pct = (d["wr"] - d_min) / d_span * 100
            is_top = d["wr"] == d_max
            cls = "meta-bar-fill head" if is_top else "meta-bar-fill"
            d_bars += (
                f'<div class="meta-row">'
                f'  <div class="meta-class">{d["difficulty"]}</div>'
                f'  <div class="meta-bar"><div class="{cls}" style="width:{max(8, pct):.0f}%"></div></div>'
                f'  <div class="meta-wr">{d["wr"]:.1f}%</div>'
                f'  <div class="meta-n">{d["n_champions"]} champs</div>'
                f'</div>'
            )
        st.markdown(
            f"""
            <div class="wr-card" style="margin: 1.5rem 0;">
              <div class="wr-card-header">
                <div class="wr-card-title">Win Rate by Difficulty &mdash; {d_headline}</div>
                <div style="color:var(--muted);font-size:0.78rem;">Games-weighted average WR per difficulty bucket</div>
              </div>
              <div class="meta-grid">{d_bars}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# --- Footer info ---------------------------------------------------------
st.write("")
if ALL_CHAMPIONS:
    st.markdown(
        f'<div style="color:var(--muted);font-size:0.85rem;text-align:center;margin-top:2rem;">'
        f'Currently tracked: {", ".join(ALL_CHAMPIONS)} '
        f'({len(df)} player{"s" if len(df) != 1 else ""})</div>',
        unsafe_allow_html=True,
    )

st.markdown(site_footer(), unsafe_allow_html=True)
