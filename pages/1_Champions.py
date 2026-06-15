"""Champions page — custom themed table with class, difficulty, tier and
the confidence-adjusted win rate. Optional class/role filters.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from web.champion_meta import CLASSES
from web.champion_roles import ROLES, roles_for
from web.components import (
    Col,
    TOP50_NOTICE,
    UPDATED_NOTICE,
    champ_cell,
    class_chip,
    difficulty_cell,
    notice_bar,
    render_table,
    site_footer,
    tier_pill,
)
from web.data_loader import (
    assign_tier,
    champion_summary,
    get_champions,
    load_leaderboard,
)
from web.style import inject_css, top_nav


st.set_page_config(
    page_title="Champions - WRTrueMeta",
    page_icon=":crossed_swords:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

df = load_leaderboard()
champions = get_champions(df) if not df.empty else []
top_nav(active="Champions", champions=champions)

st.markdown('<h1 style="margin:0.5rem 0 0.25rem;">Champions</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:var(--muted);margin-bottom:0.75rem;">'
    'Per-champion aggregates from the top 50 players we have scraped. '
    'Sorted by win rate.</p>',
    unsafe_allow_html=True,
)
st.markdown(notice_bar([UPDATED_NOTICE, TOP50_NOTICE]), unsafe_allow_html=True)

summary = champion_summary(df)
if summary.empty:
    st.info("No champion data yet. Run the scraper to populate.")
    st.stop()

# --- Filters -----------------------------------------------------------
fc1, fc2, fc3, fc4 = st.columns([1, 1, 1.2, 1.6])
with fc1:
    role_filter = st.selectbox("Role", ["All roles", *ROLES], index=0)
with fc2:
    class_filter = st.selectbox("Class", ["All classes", *CLASSES], index=0)
with fc3:
    sort_by = st.selectbox(
        "Sort by",
        ("Win Rate", "Ceiling WR", "Difficulty",
         "Total Games", "Top Mastery", "Name"),
        index=0,
    )
with fc4:
    search = st.text_input("Search champion", "")

view = summary.copy()
if role_filter != "All roles":
    view = view[view["champion"].apply(lambda c: role_filter in roles_for(c))]
if class_filter != "All classes":
    view = view[view["champ_class"] == class_filter]
if search.strip():
    view = view[view["champion"].str.contains(search.strip(), case=False, na=False)]

# Sorting. Most metrics are "higher is better" (descending); Name is A→Z.
_sort_map = {
    "Win Rate": ("weighted_winrate", False),
    "Ceiling WR": ("max_winrate", False),
    "Difficulty": ("difficulty", False),
    "Total Games": ("total_games", False),
    "Top Mastery": ("max_score", False),
    "Name": ("champion", True),
}
_scol, _asc = _sort_map[sort_by]
view = view.sort_values(_scol, ascending=_asc, na_position="last").reset_index(drop=True)

if view.empty:
    st.info("No champions match those filters.")
    st.stop()

# --- Build rows --------------------------------------------------------
rows = []
for i, r in view.iterrows():
    tier_label, tier_class = assign_tier(r["weighted_winrate"])
    rows.append({
        "rank": i + 1,
        "champion": r["champion"],
        "tier_label": tier_label,
        "tier_class": tier_class,
        "champ_class": r["champ_class"],
        "difficulty": int(r["difficulty"]),
        "wr": r["weighted_winrate"],
        "ceiling": r["max_winrate"],
        "total_games": r["total_games"],
        "top_mastery": r["max_score"],
        "rank1": r["top_player"],
        "n_players": r["n_players"],
    })


def _wr(v) -> str:
    return f'<span style="color:var(--accent);font-weight:700;">{v:.1f}%</span>' if pd.notna(v) else "—"


def _int(v) -> str:
    return f"{int(round(v)):,}" if pd.notna(v) else "—"


columns = [
    Col("#", lambda r: f'<span class="cell-rank">{r["rank"]}</span>', "center"),
    Col("Champion", lambda r: champ_cell(r["champion"])),
    Col("Tier", lambda r: tier_pill(r["tier_label"], r["tier_class"]), "center"),
    Col("Class", lambda r: class_chip(r["champ_class"]), "center"),
    Col("Difficulty", lambda r: difficulty_cell(r["difficulty"]), "center"),
    Col("Win Rate", lambda r: _wr(r["wr"]), "num"),
    Col("Ceiling", lambda r: f'{r["ceiling"]:.1f}%' if pd.notna(r["ceiling"]) else "—", "num"),
    Col("Total Games", lambda r: _int(r["total_games"]), "num"),
    Col("Top Mastery", lambda r: _int(r["top_mastery"]), "num"),
    Col("Rank 1", lambda r: str(r["rank1"]) if pd.notna(r["rank1"]) else "—"),
]

# Gold/silver/bronze only makes sense when sorted by win rate.
_hl = 3 if sort_by == "Win Rate" else 0
st.markdown(render_table(columns, rows, highlight_top=_hl), unsafe_allow_html=True)

st.markdown(site_footer(), unsafe_allow_html=True)
