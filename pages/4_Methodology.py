"""Methodology page — explains how every number on the site is computed."""
from __future__ import annotations

import streamlit as st

from web.components import site_footer
from web.data_loader import (
    FLOOR_MAX,
    FLOOR_MIN,
    SHRINKAGE_C,
    TOP_N_PLAYERS,
    get_champions,
    load_leaderboard,
)
from web.style import inject_css, top_nav


st.set_page_config(
    page_title="Methodology - WRTrueMeta",
    page_icon=":book:",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

df = load_leaderboard()
champions = get_champions(df) if not df.empty else []
top_nav(active="Methodology", champions=champions)

st.markdown('<h1 style="margin:0.5rem 0 0.25rem;">How this works</h1>', unsafe_allow_html=True)
st.markdown(
    '<p style="color:var(--muted);margin-bottom:1.5rem;max-width:760px;">'
    'Every number here comes from real in-game leaderboard data, not public '
    'match samples. This page explains exactly how each stat is built so you '
    'can judge it for yourself.</p>',
    unsafe_allow_html=True,
)


def section(title: str, body_html: str) -> None:
    st.markdown(
        f"""
        <div class="wr-card" style="margin-bottom: 1.1rem;">
          <div class="wr-card-header"><div class="wr-card-title">{title}</div></div>
          <div style="color:rgba(230,236,255,0.9);font-size:0.95rem;line-height:1.6;">
            {body_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


section(
    "Where the data comes from",
    "We read each champion&rsquo;s in-game <strong>Champion &amp; Lane</strong> "
    "leaderboard directly from a phone running Wild Rift, via screen capture + "
    "OCR. For every champion we record the top players: their mastery score, "
    "games played, and win rate on that champion. Data refreshes "
    "<strong>twice a month</strong>.",
)

section(
    f"Why the top {TOP_N_PLAYERS} players",
    f"We aggregate over each champion&rsquo;s <strong>top {TOP_N_PLAYERS}</strong> "
    "players. That&rsquo;s deep enough to be a real sample but shallow enough "
    "that everyone in it is genuinely a high-level specialist on the champion "
    "&mdash; which is the population whose win rate actually tells you how "
    "strong the champion is in expert hands.",
)

section(
    "Champion win rate (the headline number)",
    "A raw average of 50 players&rsquo; win rates is easy to distort: a smurf "
    "with 8 games at 90% would drag it up. So we use a three-step pipeline:"
    "<ol style='margin:0.6rem 0 0;padding-left:1.2rem;'>"
    "<li><strong>Entry floor</strong> &mdash; a player needs enough games on the "
    f"champion to count at all. The floor scales with how much that champion is "
    f"played (30% of its median games, clamped to {FLOOR_MIN}&ndash;{FLOOR_MAX}), "
    "because a niche pick&rsquo;s mains have far fewer games than a meta "
    "blind-pick&rsquo;s.</li>"
    "<li><strong>Bayesian shrinkage</strong> &mdash; each player&rsquo;s win rate "
    f"is pulled toward the champion&rsquo;s own average by {SHRINKAGE_C} games of "
    "synthetic evidence: <code>adj = (wins + C&middot;prior) / (games + C)</code>. "
    "So 10 games at 70% becomes ~55%, while 400 games at 60% stays ~59% &mdash; "
    "small samples get muted, big ones speak for themselves.</li>"
    "<li><strong>Capped weighting</strong> &mdash; we then average the adjusted "
    "rates weighting by games, but cap each player&rsquo;s weight at the "
    "champion&rsquo;s 75th-percentile games. A 900-game spammer can&rsquo;t "
    "single-handedly own the number.</li>"
    "</ol>",
)

section(
    "Best player on a champion",
    "&ldquo;Best&rdquo; isn&rsquo;t just the highest win rate &mdash; that would "
    "always be whoever got lucky over a handful of games. We rank by the "
    "<strong>Wilson score lower bound</strong>: the conservative end of a 95% "
    "confidence interval on a player&rsquo;s true win rate. A 3-game 100% run "
    "scores ~44% (huge uncertainty); a 134-game 67% main scores ~59% (tight "
    "interval). The title goes to demonstrated, high-volume performance.",
)

section(
    "Tiers",
    "Champions are bucketed <strong>GOD &middot; S &middot; A &middot; B &middot; "
    "C &middot; Ass</strong> purely by their confidence-adjusted win rate. "
    "Cutoffs: GOD 63%+, S 61&ndash;63%, A 59&ndash;61%, B 57&ndash;59%, "
    "C 56&ndash;57%, Ass under 56%. These are tuned for top-50 win rates, which "
    "run higher than the general-population 50% baseline.",
)

section(
    "How big is a big gap?",
    "<p style='margin:0 0 0.8rem;'>Top-50 win rates cluster in a tight band "
    "(usually 55&ndash;64%) because everyone in the sample is already an elite "
    "main. Small numerical gaps can mean a lot &mdash; here&rsquo;s how to read "
    "them:</p>"
    "<p style='margin:0 0 0.8rem;'><strong>Translation:</strong> each percentage "
    "point of win rate <strong>&asymp; one extra win per 100 games</strong> on "
    "that champion. So a 4-point gap means roughly one extra win every 25 games "
    "&mdash; that&rsquo;s the kind of difference you actually feel.</p>"
    "<div style='overflow-x:auto;'>"
    "<table style='width:100%;border-collapse:collapse;font-size:0.9rem;"
    "color:rgba(230,236,255,0.9);'>"
    "<thead><tr style='color:var(--muted);font-size:0.72rem;letter-spacing:0.12em;"
    "text-transform:uppercase;text-align:left;'>"
    "<th style='padding:0.5rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.1);'>Gap</th>"
    "<th style='padding:0.5rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.1);'>What it means</th>"
    "</tr></thead><tbody>"
    "<tr><td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'><strong>&lt; 1 pt</strong></td>"
    "<td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'>Noise &mdash; within statistical error. Treat as a tie.</td></tr>"
    "<tr><td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'><strong>1&ndash;2 pts</strong></td>"
    "<td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'>Small but real, often same tier.</td></tr>"
    "<tr><td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'><strong>~2 pts</strong></td>"
    "<td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'>One tier boundary. By design &mdash; that&rsquo;s how the tiers are spaced.</td></tr>"
    "<tr><td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'><strong>3&ndash;4 pts</strong></td>"
    "<td style='padding:0.45rem 0.7rem;border-bottom:1px solid rgba(255,255,255,0.05);'>Clearly better at high level. ~1 extra win per 25&ndash;33 games.</td></tr>"
    "<tr><td style='padding:0.45rem 0.7rem;'><strong>5+ pts</strong></td>"
    "<td style='padding:0.45rem 0.7rem;'>Dominant &mdash; two-plus tiers apart. The gap between GOD and bottom tiers.</td></tr>"
    "</tbody></table></div>"
    "<p style='margin:0.8rem 0 0;color:var(--muted);font-size:0.85rem;'>"
    "Quick rule of thumb: <strong>2 pts = one tier</strong>, <strong>4 pts = "
    "clearly stronger</strong>, <strong>5+ pts = dominant</strong>. Inside 1 pt, "
    "pick whichever champion you&rsquo;re more comfortable on.</p>",
)

section(
    "Role &amp; class averages, and &ldquo;the meta&rdquo;",
    "Role and class win rates are the games-weighted average of their member "
    "champions&rsquo; adjusted win rates, so a class carried by heavily-played "
    "champions reads stronger. We flag any role or class backed by only a few "
    "scraped champions as <strong>low-confidence</strong> rather than presenting "
    "it as authoritative. The headline &ldquo;meta&rdquo; is the highest-win-rate "
    "class that has enough champions behind it to be trustworthy.",
)

section(
    "Strong off-meta (sleeper) picks",
    "We don&rsquo;t have true ladder-wide pick rates &mdash; we scrape exactly "
    "the top 50 of <em>every</em> champion, popular or not. So for &ldquo;few "
    "people play it&rdquo; we use <strong>mastery depth</strong> as a proxy: the "
    "median mastery score of a champion&rsquo;s top 50 is the &ldquo;entry "
    "bar&rdquo; to being elite on it. A heavily-contested champion has a high "
    "bar; a niche one has a low bar. A sleeper pick is one in the bottom ~40% of "
    "mastery depth that still posts a top-40% win rate. (Caveat: a brand-new "
    "champion can show up here just because nobody&rsquo;s had time to grind "
    "mastery yet.)",
)

section(
    "Player names",
    "Names are read by OCR. Latin names usually come through cleanly, but "
    "special characters and non-Latin scripts (Chinese, Korean, Arabic, &hellip;) "
    "often don&rsquo;t &mdash; those are shown as "
    "<code>SomeChineseName</code>. Treat names as best-effort, not gospel.",
)

section(
    "Difficulty &amp; class",
    "Each champion&rsquo;s combat class (Tank / Bruiser / Assassin / Mage / "
    "Marksman / Enchanter) and 1&ndash;10 difficulty rating are editorial "
    "judgement calls based on kit and mechanical ceiling &mdash; not derived "
    "from the data. They&rsquo;re there to give context, not to be precise.",
)

st.markdown(
    '<p style="color:var(--muted);font-size:0.85rem;text-align:center;margin-top:1.5rem;">'
    'Spot an error? This is a fan project &mdash; the numbers are only as good '
    'as the data and the assumptions above.</p>',
    unsafe_allow_html=True,
)

st.markdown(site_footer(), unsafe_allow_html=True)
