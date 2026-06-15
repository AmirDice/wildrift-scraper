"""Leaderboard page - top players per champion from the scraped CSV.

Layout:
    [ splash card | styled table + filters ]

The splash card on the left uses the champion's full-body DDragon loading
art with a slow Ken-Burns pan, and the stats overlay reacts to the table
selection: when a player row is clicked, the four stats become that
player's rank / win-rate / mastery / games (instead of aggregates).
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from web.champion_assets import splash_url
from web.champion_card import render_champion_card
from web.champion_meta import champion_class
from web.champion_roles import roles_for
from web.components import (
    BEST_BUILDS_NOTICE,
    Col,
    NA_WINRATES_NOTICE,
    TOP50_NOTICE,
    UPDATED_NOTICE,
    consistency_label,
    notice_bar,
    notice_pill,
    render_table,
    site_footer,
    winrate_distribution_svg,
)
from web.data_loader import (
    assign_tier,
    best_player_per_champion,
    champion_summary,
    get_champions,
    load_leaderboard,
)
from web.style import inject_css, top_nav


st.set_page_config(
    page_title="Leaderboard - WRTrueMeta",
    page_icon=":trophy:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

df = load_leaderboard()
champions = get_champions(df) if not df.empty else []
top_nav(active="Leaderboard", champions=champions)

st.markdown('<h1 style="margin:0.5rem 0 0.25rem;">Leaderboard</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:var(--muted);margin-bottom:0.75rem;">Top-ranked players for each champion.</p>',
    unsafe_allow_html=True,
)
# Refresh-cadence + top-50 explainer + name-accuracy notices.
_name_notice = notice_pill(
    "Some names may be off &mdash; special characters &amp; non-Latin scripts "
    "don&rsquo;t always read cleanly", icon="&#9888;", kind="gold",
)
st.markdown(
    notice_bar([UPDATED_NOTICE, TOP50_NOTICE, _name_notice,
                NA_WINRATES_NOTICE, BEST_BUILDS_NOTICE]),
    unsafe_allow_html=True,
)

if df.empty:
    st.info(
        "No leaderboard data yet. Run "
        "`python -m src.scrape_timed --target Aatrox --n 200` to populate."
    )
    st.stop()

# --- Champion default driven by `?champion=` query param ----------------
qp_champ = st.query_params.get("champion", "")
if qp_champ:
    match = next((c for c in champions if c.lower() == qp_champ.strip().lower()), None)
    default_index = champions.index(match) if match else 0
else:
    default_index = 0

# --- Filters (full width, above the splash + table) --------------------
fc1, fc2, fc3 = st.columns([2, 1, 1])
with fc1:
    champion = st.selectbox("Champion", champions, index=default_index, key="lb_champion")
with fc2:
    top_n = st.number_input("Show top N", min_value=10, max_value=500, value=100, step=10)
with fc3:
    sort_by = st.selectbox(
        "Sort by",
        ("Rank (in-game)", "Best player score", "Mastery score", "Win rate", "Games"),
    )

# Sync ?champion= back to the URL when the user picks a different champ
# (keeps shareable URLs accurate).
if st.query_params.get("champion") != champion:
    st.query_params["champion"] = champion

# Filter and sort.
sub = df[df["champion"] == champion].copy()

# Confidence-adjusted "best player score" (Wilson lower-bound WR) needs to
# exist on every row BEFORE the sort/top-N cut, otherwise sorting on it would
# only consider whatever default order survived the head().
_score_df = best_player_per_champion(sub)
sub = sub.merge(
    _score_df[["rank", "confidence_wr"]], on="rank", how="left"
)

sort_map = {
    "Rank (in-game)":     ("rank", True),
    "Best player score":  ("confidence_wr", False),
    "Mastery score":      ("score", False),
    "Win rate":           ("winrate", False),
    "Games":              ("games", False),
}
sort_col, ascending = sort_map[sort_by]
sub = sub.sort_values(sort_col, ascending=ascending, na_position="last").head(int(top_n)).reset_index(drop=True)

# Canonical champion stats (top-50, games-weighted) — pulled from the same
# summary that powers the tier list so the tier shown here matches exactly.
champ_rows = df[df["champion"] == champion]
_csum = champion_summary(df)
_crow = _csum[_csum["champion"] == champion]
if not _crow.empty:
    agg_weighted_wr = float(_crow.iloc[0]["weighted_winrate"])
    agg_max_wr = float(_crow.iloc[0]["max_winrate"])
    # Median, not mean: one 900-game spammer shouldn't inflate the number.
    agg_med_games = float(_crow.iloc[0]["median_games"])
else:
    agg_weighted_wr = sub["winrate"].mean()
    agg_max_wr = sub["winrate"].max()
    agg_med_games = sub["games"].median()
tier_label, tier_class = assign_tier(agg_weighted_wr)

# "Best player" — Wilson score lower bound, so the title goes to demonstrated
# high-volume performance rather than a few lucky games. Computed over the
# champion's top-50 players (best_player_per_champion filters internally).
best_df = best_player_per_champion(champ_rows)
best_subset = best_df[best_df["is_best_for_champ"]]
best_row = best_subset.iloc[0] if not best_subset.empty else None


def _fmt_wr(x) -> str:
    return f"{x:.1f}%" if pd.notna(x) else "—"


def _fmt_int(x) -> str:
    return f"{int(round(x)):,}" if pd.notna(x) else "—"


# --- Layout: splash placeholder on left, table on right ----------------
left_col, right_col = st.columns([1, 2.2], gap="large")

with left_col:
    splash_slot = st.empty()
    share_slot = st.container()

# Player highlight selector drives the splash card (replaces the old
# click-to-select on the default dataframe).
player_opts = ["Champion overview"] + [
    f"#{int(r['rank'])}  {r['player_name']}" for _, r in sub.iterrows()
]
selected_row = None
with right_col:
    pick = st.selectbox("Highlight a player", player_opts, index=0, key="lb_player")
    if pick != "Champion overview":
        sel_idx = player_opts.index(pick) - 1
        if 0 <= sel_idx < len(sub):
            selected_row = sub.iloc[sel_idx]

    # Build the themed table.
    sel_name = str(selected_row["player_name"]) if selected_row is not None else None
    table_rows = []
    for _, r in sub.iterrows():
        table_rows.append({
            "rank": int(r["rank"]) if pd.notna(r["rank"]) else "—",
            "player": str(r["player_name"]),
            "mastery": r["score"],
            "games": r["games"],
            "wr": r["winrate"],
            "is_sel": (sel_name is not None and str(r["player_name"]) == sel_name),
        })

    def _player_cell(row):
        star = ' <span style="color:var(--accent);">&#9733;</span>' if row["is_sel"] else ""
        return f'{row["player"]}{star}'

    cols = [
        Col("#", lambda r: f'<span class="cell-rank">{r["rank"]}</span>', "center"),
        Col("Player", _player_cell),
        Col("Mastery", lambda r: f'{int(r["mastery"]):,}' if pd.notna(r["mastery"]) else "—", "num"),
        Col("Games", lambda r: f'{int(r["games"]):,}' if pd.notna(r["games"]) else "—", "num"),
        Col("Win Rate", lambda r: (
            f'<span style="color:var(--accent);font-weight:700;">{r["wr"]:.1f}%</span>'
            if pd.notna(r["wr"]) else "—"
        ), "num"),
    ]
    # Only show the score column when the user sorted by it, to avoid bloating
    # the default view.
    if sort_by == "Best player score":
        # Inject the score into each row dict so the column renderer can find it.
        for tr, (_, srow) in zip(table_rows, sub.iterrows()):
            tr["score_wilson"] = srow.get("confidence_wr")
        cols.append(Col(
            "Best Player Score",
            lambda r: (f'<span style="color:var(--gold-bright);font-weight:700;">'
                       f'{r["score_wilson"]:.1f}</span>'
                       if pd.notna(r.get("score_wilson")) else "—"),
            "num",
        ))
    st.markdown(render_table(cols, table_rows, scroll=True), unsafe_allow_html=True)

    # --- Win-rate consistency line chart (sits right under the table) ----
    wr_vals = sub["winrate"].dropna().astype(float).tolist()
    cons_label, cons_sd = consistency_label(wr_vals)
    dist_svg = winrate_distribution_svg(wr_vals)
    st.markdown(
        f"""
        <div class="wr-card" style="margin-top: 1rem;">
          <div class="wr-card-header">
            <div class="wr-card-title">Win-Rate Distribution</div>
            <div style="color:var(--muted);font-size:0.78rem;">
              {cons_label}{'' if cons_sd == 0 else f' &nbsp;·&nbsp; &sigma; = {cons_sd:.1f} pts'}
            </div>
          </div>
          {dist_svg}
          <div style="color:var(--muted);font-size:0.76rem;margin-top:0.5rem;line-height:1.5;">
            How the top {len(wr_vals)} players&rsquo; win rates spread out. A tall,
            narrow peak means the champion wins consistently for anyone skilled;
            a wide, flat curve means it&rsquo;s carry-or-feed.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Fill the splash placeholder with selection-aware content ----------
splash_bg_style = (
    f"background-image: url('{splash_url(champion)}');"
    "background-position: center 18%;"
)

if selected_row is not None:
    # Player-specific stats
    p_rank = int(selected_row["rank"])
    p_name = str(selected_row["player_name"] or "Unknown")
    p_wr = selected_row["winrate"]
    p_mastery = selected_row["score"]
    p_games = selected_row["games"]
    eyebrow = f"RANK #{p_rank} &middot; {champion}"
    big_name = p_name
    sub_name = f"Top {top_n} {champion} player"
    # 2x2 stats grid for the selected player
    stats_html = f"""
        <div>
            <div class="stat-label">Win Rate</div>
            <div class="stat-value accent">{_fmt_wr(p_wr)}</div>
        </div>
        <div>
            <div class="stat-label">Mastery</div>
            <div class="stat-value gold">{_fmt_int(p_mastery)}</div>
        </div>
        <div>
            <div class="stat-label">Games</div>
            <div class="stat-value">{_fmt_int(p_games)}</div>
        </div>
        <div>
            <div class="stat-label">Rank</div>
            <div class="stat-value">#{p_rank}</div>
        </div>
    """
else:
    # Aggregate stats (default view)
    eyebrow = "Top Players"
    big_name = champion
    if best_row is not None:
        best_name = str(best_row.get("player_name") or "Unknown")
        best_rank = int(best_row["rank"]) if pd.notna(best_row["rank"]) else None
        sub_name = (
            f"Best player: {best_name}"
            + (f" &middot; rank #{best_rank}" if best_rank is not None else "")
        )
    else:
        sub_name = f"Showing top {len(sub)}"
    stats_html = f"""
        <div>
            <div class="stat-label">Tier</div>
            <div class="stat-value {tier_class}">{tier_label}</div>
        </div>
        <div>
            <div class="stat-label">Win Rate</div>
            <div class="stat-value accent">{_fmt_wr(agg_weighted_wr)}</div>
        </div>
        <div>
            <div class="stat-label">Ceiling WR</div>
            <div class="stat-value">{_fmt_wr(agg_max_wr)}</div>
        </div>
        <div>
            <div class="stat-label">Median Games</div>
            <div class="stat-value">{_fmt_int(agg_med_games)}</div>
        </div>
    """

with splash_slot.container():
    st.markdown(
        f"""
        <div class="splash-card">
            <div class="splash-card-bg" style="{splash_bg_style}"></div>
            <div class="splash-card-eyebrow">{eyebrow}</div>
            <div class="splash-card-name">{big_name}</div>
            <div class="splash-card-sub">{sub_name}</div>
            <div class="splash-stats">
                <div class="stats-grid">{stats_html}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Share this champion card ------------------------------------------
with share_slot:
    with st.expander("Share this champion", expanded=False):
        share_url = f"https://wrtruemeta.com/Leaderboard?champion={champion}"
        st.markdown(
            '<div style="color:var(--muted);font-size:0.82rem;margin-bottom:0.4rem;">'
            'Shareable link &mdash; opens straight to this champion:</div>',
            unsafe_allow_html=True,
        )
        st.code(share_url, language=None)
        if st.button("Generate share card (PNG)", use_container_width=True, key="gen_card"):
            with st.spinner("Rendering card..."):
                png = render_champion_card(
                    champion=champion,
                    tier=tier_label,
                    win_rate=agg_weighted_wr if pd.notna(agg_weighted_wr) else None,
                    ceiling_wr=agg_max_wr if pd.notna(agg_max_wr) else None,
                    median_games=agg_med_games if pd.notna(agg_med_games) else None,
                    best_player=(str(best_row["player_name"]) if best_row is not None else None),
                    best_player_wr=(float(best_row["confidence_wr"])
                                    if best_row is not None and pd.notna(best_row.get("confidence_wr"))
                                    else None),
                    champ_class=champion_class(champion),
                    role=roles_for(champion)[0],
                )
            st.session_state["_champ_card_png"] = png
            st.session_state["_champ_card_name"] = champion
        if st.session_state.get("_champ_card_name") == champion and "_champ_card_png" in st.session_state:
            st.image(st.session_state["_champ_card_png"], use_container_width=True)
            st.download_button(
                "Download card",
                data=st.session_state["_champ_card_png"],
                file_name=f"wrtruemeta_{champion.lower().replace(' ', '_')}.png",
                mime="image/png",
                use_container_width=True,
            )

st.markdown(site_footer(), unsafe_allow_html=True)
