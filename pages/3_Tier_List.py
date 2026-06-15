"""Tier List page - champions bucketed by mean winrate.

Each champion's mean win rate (across the top players scraped for them) is
mapped to a tier via `data_loader.assign_tier`. A role filter narrows the
list to just one of {Baron, Jungle, Mid, Dragon, Support}. The "Save as
image" button downloads a PNG with the WrTrueMeta logo watermarked.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from web.champion_assets import icon_url
from web.champion_meta import champion_difficulty, difficulty_label
from web.champion_roles import ROLES, roles_for
from web.components import GAP_NOTICE, TOP50_NOTICE, notice_bar, site_footer
from web.data_loader import (
    assign_tier,
    assign_tier_relative,
    champion_summary,
    get_champions,
    load_leaderboard,
    tier_order,
)
from web.style import inject_css, top_nav
from web.tier_image import render_tier_list_png


st.set_page_config(
    page_title="Tier List - WRTrueMeta",
    page_icon=":trophy:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

df = load_leaderboard()
champions = get_champions(df) if not df.empty else []
top_nav(active="Tier List", champions=champions)

st.markdown('<h1 style="margin:0.5rem 0 0.25rem;">Tier List</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:var(--muted);margin-bottom:0.75rem;">'
    'Champions ranked by the confidence-adjusted win rate of their top 50 '
    'players: a games floor scaled to each champion&rsquo;s play volume, small '
    'samples shrunk toward the champion average, and no single spammer can '
    'own the number. Higher WR = higher tier.</p>',
    unsafe_allow_html=True,
)
st.markdown(notice_bar([TOP50_NOTICE, GAP_NOTICE]), unsafe_allow_html=True)

if df.empty:
    st.info(
        "No data yet. Run "
        "`python -m src.scrape_timed --target Aatrox --n 200` to populate."
    )
    st.stop()

summary = champion_summary(df)
if summary.empty:
    st.info("No champion summary available.")
    st.stop()

# --- Role filter --------------------------------------------------------
filter_col, dl_col = st.columns([3, 1])
with filter_col:
    role_options = ["All roles", *ROLES]
    role_filter = st.selectbox("Filter by role", role_options, index=0)


# Apply role filter
if role_filter != "All roles":
    summary = summary[summary["champion"].apply(
        lambda c: role_filter in roles_for(c)
    )].reset_index(drop=True)


# Group champions by tier, within each tier sort by weighted WR desc.
# When a single role is selected we use PERCENTILE-based cutoffs so the role
# gets a full GOD-to-Ass spread (the absolute cutoffs leave most roles with
# no GOD or no Ass champion). All-roles view uses the static cutoffs.
pool_wrs = summary["weighted_winrate"].dropna().astype(float).tolist()
_tier_func = (
    (lambda w: assign_tier_relative(w, pool_wrs))
    if role_filter != "All roles"
    else assign_tier
)
buckets: dict[str, list[tuple[str, float, bool, bool]]] = {label: [] for label, _ in tier_order()}
for _, row in summary.sort_values("weighted_winrate", ascending=False).iterrows():
    name = str(row["champion"])
    wr = row["weighted_winrate"]
    if pd.isna(wr):
        continue
    label, _klass = _tier_func(float(wr))
    diff_label = difficulty_label(champion_difficulty(name))
    is_hard = diff_label in ("Hard", "Very Hard")
    buckets[label].append((
        name, float(wr), bool(row.get("is_otp", False)), is_hard
    ))


# --- Save-as-image button ----------------------------------------------
def _build_filename() -> str:
    role_part = role_filter.lower().replace(" ", "_") if role_filter != "All roles" else "all"
    return f"wrtruemeta_tier_list_{role_part}.png"


with dl_col:
    st.write("")  # vertical alignment with the selectbox
    if st.button("Generate downloadable image", use_container_width=True):
        subtitle = (
            f"Filter: {role_filter}"
            if role_filter != "All roles"
            else "All champions"
        )
        with st.spinner("Rendering..."):
            png_bytes = render_tier_list_png(buckets, subtitle=subtitle)
        st.session_state["_tier_image"] = png_bytes
        st.session_state["_tier_image_name"] = _build_filename()

    if "_tier_image" in st.session_state:
        st.download_button(
            "Download PNG",
            data=st.session_state["_tier_image"],
            file_name=st.session_state.get("_tier_image_name", "wrtruemeta_tier_list.png"),
            mime="image/png",
            use_container_width=True,
        )


# --- Render the tier grid ----------------------------------------------
def _render_champ(name: str, wr: float, is_otp: bool, is_hard: bool) -> str:
    tags = []
    if is_otp:
        tags.append("OTP")
    if is_hard:
        tags.append("hard to play")
    title = f"{name} - {wr:.1f}% WR" + (" - " + ", ".join(tags) if tags else "")
    badge = ('<span class="otp-badge" title="One-Trick-Pony: heavily-skewed player base">OTP</span>'
             if is_otp else "")
    icon_cls = "tier-champ-icon" + (" diff-hard" if is_hard else "")
    return (
        f'<div class="tier-champ" title="{title}">'
        f'  <div class="{icon_cls}">'
        f'    <img src="{icon_url(name)}" alt="{name}" />'
        f'    {badge}'
        f'  </div>'
        f'  <div class="champ-name">{name}</div>'
        f'  <div class="champ-wr">{wr:.1f}%</div>'
        f'</div>'
    )


rows_html = []
for label, css_class in tier_order():
    champs = buckets.get(label, [])
    if champs:
        champ_html = "".join(_render_champ(*c) for c in champs)
    else:
        champ_html = '<div class="tier-empty">No champions in this tier yet.</div>'
    rows_html.append(
        f'<div class="tier-row">'
        f'  <div class="tier-label {css_class}">{label}</div>'
        f'  <div class="tier-champs">{champ_html}</div>'
        f'</div>'
    )

st.markdown(
    f'<div class="tier-grid">{"".join(rows_html)}</div>',
    unsafe_allow_html=True,
)

# Tier-cutoff legend at the bottom.
if role_filter == "All roles":
    cutoff_title = "Tier cutoffs (confidence-adjusted win rate, top 50 players)"
    cutoff_body = (
        "GOD: 63%+ &nbsp;·&nbsp; S: 61-63% &nbsp;·&nbsp; A: 59-61% &nbsp;·&nbsp; "
        "B: 57-59% &nbsp;·&nbsp; C: 56-57% &nbsp;·&nbsp; Ass: under 56%"
    )
else:
    cutoff_title = f"Tier cutoffs &mdash; percentile-based within {role_filter}"
    cutoff_body = (
        "GOD: top 8% &nbsp;·&nbsp; S: next 17% &nbsp;·&nbsp; A: next 25% &nbsp;·&nbsp; "
        "B: next 25% &nbsp;·&nbsp; C: next 17% &nbsp;·&nbsp; Ass: bottom 8%"
        f" &nbsp;&middot;&nbsp; <span style='color:var(--muted);'>"
        f"a {role_filter}'s WR range is narrower than the full pool, so cutoffs "
        f"adapt to keep every tier populated</span>"
    )
st.markdown(
    f'<div style="margin-top:1.5rem;padding:1rem 1.25rem;background:var(--card);'
    f'border:1px solid var(--border);border-radius:10px;">'
    f'<div style="color:var(--muted);font-size:0.7rem;letter-spacing:0.12em;'
    f'text-transform:uppercase;font-weight:700;margin-bottom:0.5rem;">{cutoff_title}</div>'
    f'<div style="color:var(--text);font-size:0.9rem;">{cutoff_body}</div></div>',
    unsafe_allow_html=True,
)

st.markdown(site_footer(), unsafe_allow_html=True)
