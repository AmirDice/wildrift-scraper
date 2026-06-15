"""Custom CSS for the WRTrueMeta Streamlit app.

Centralizes the dark-navy + blue-accent theme so every page calls
`inject_css()` once at the top after `st.set_page_config()`.
"""
from __future__ import annotations

import streamlit as st


CUSTOM_CSS = """
<style>
:root {
    --bg: #070b18;
    --bg-2: #0c1226;
    --card: #121a30;
    --card-2: #1a2240;
    --border: #1f2940;
    --text: #e6ecff;
    --muted: #8a92a8;
    --accent: #4a90ff;
    --accent-dim: #2b5ac0;
    --gold: #d4a64a;
    --gold-bright: #ffe188;
    --silver: #c9d0e0;
    --bronze: #cd884a;
    --green: #2e8a5a;
}

/* Hide Streamlit chrome */
#MainMenu, footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* App background — pre-blurred Wild Rift art with a LIGHT dark overlay so
   the colour actually shows through. The image itself is heavily Gaussian-
   blurred at build time (see static/page_bg.jpg), so we don't need much
   gradient to keep cards readable — the cards add their own backdrop blur.
   Landing page injects its own .stApp bg AFTER inject_css() so its hero
   treatment wins via later cascade. */
.stApp {
    background:
      linear-gradient(180deg, rgba(7,11,24,0.42) 0%, rgba(7,11,24,0.62) 100%),
      url('/app/static/page_bg.jpg') no-repeat center center / cover fixed,
      radial-gradient(circle at 18% -10%, rgba(74,144,255,0.12), transparent 55%),
      radial-gradient(circle at 82% 110%, rgba(74,144,255,0.08), transparent 55%),
      var(--bg);
    color: var(--text);
}
/* Headings sit directly on the page bg (cards have their own glass), so
   add a subtle text shadow for legibility now that the overlay is lighter. */
.main h1, .main h2, .main h3 {
    text-shadow: 0 2px 14px rgba(0,0,0,0.55);
}
.main .block-container { padding-top: 1rem; padding-bottom: 3rem; max-width: 1280px; }

/* --- Top navigation bar — sticky frosted glass --- */
.wr-nav {
    display: flex; align-items: center; gap: 1.25rem;
    padding: 0.4rem 1.5rem;
    margin: -1rem -1rem 1.75rem;
    position: sticky; top: 0; z-index: 999;
    background: rgba(8, 12, 26, 0.78);
    backdrop-filter: blur(20px) saturate(140%);
    -webkit-backdrop-filter: blur(20px) saturate(140%);
    border-bottom: 1px solid rgba(255,255,255,0.07);
    box-shadow: 0 6px 28px rgba(0,0,0,0.35);
}
/* faint accent line riding the bottom edge */
.wr-nav::after {
    content: ''; position: absolute; left: 0; right: 0; bottom: -1px; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(74,144,255,0.55), transparent);
}
.brand {
    display: flex; align-items: center;
    text-decoration: none;
    flex-shrink: 0;
    height: 84px;
    transition: filter 0.18s, transform 0.18s;
}
.brand:hover { filter: drop-shadow(0 0 14px rgba(74,144,255,0.5)); transform: translateY(-1px); }
.brand img {
    height: 80px;
    width: auto;
    display: block;
    filter: drop-shadow(0 3px 10px rgba(0,0,0,0.6));
}
.brand-mark {
    display: inline-block; width: 22px; height: 22px;
    background: linear-gradient(135deg, var(--accent), #7aaaff);
    clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%);
}
.brand-accent { color: var(--accent); }

.wr-nav-links { display: flex; gap: 0.3rem; flex: 1; justify-content: center; }
.wr-nav-links a {
    position: relative;
    color: var(--muted); text-decoration: none;
    font-size: 0.92rem; font-weight: 600; letter-spacing: 0.01em;
    padding: 0.55rem 1rem; border-radius: 9px;
    transition: color 0.15s, background 0.15s;
}
.wr-nav-links a:hover { color: var(--text); background: rgba(255,255,255,0.05); }
.wr-nav-links a.active { color: var(--accent); }
.wr-nav-links a.active::after {
    content: ''; position: absolute; left: 1rem; right: 1rem; bottom: 0.2rem; height: 2px;
    background: linear-gradient(90deg, transparent, var(--accent), transparent);
    border-radius: 2px;
    box-shadow: 0 0 8px rgba(74,144,255,0.7);
}

/* --- Champion search form (used in nav AND hero) --- */
.champ-search {
    display: flex; align-items: center;
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 11px;
    padding-left: 0.7rem;
    overflow: hidden;
    transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}
.champ-search:focus-within {
    border-color: rgba(74,144,255,0.5);
    background: rgba(74,144,255,0.06);
    box-shadow: 0 0 0 3px rgba(74,144,255,0.14);
}
.champ-search .search-icon {
    width: 15px; height: 15px; flex-shrink: 0;
    opacity: 0.55; color: var(--muted);
}
.champ-search input {
    flex: 1; min-width: 0;
    background: transparent; border: none; outline: none;
    color: var(--text); padding: 0.5rem 0.6rem;
    font-size: 0.88rem; font-family: inherit;
}
.champ-search input::placeholder { color: var(--muted); }
.champ-search button {
    background: var(--accent); color: white; border: none;
    padding: 0 1.15rem; cursor: pointer; align-self: stretch;
    font-weight: 700; font-family: inherit; font-size: 0.84rem;
    transition: background 0.15s;
}
.champ-search button:hover { background: #5fa0ff; }
/* Nav variant — fixed width, small */
.wr-nav .champ-search { width: 290px; flex-shrink: 0; }

/* --- Hero --- */
.hero { text-align: center; padding: 3rem 1rem 1.5rem; }
.hero h1 {
    font-size: 3.2rem; font-weight: 800; margin: 0 0 0.75rem;
    letter-spacing: -0.02em; line-height: 1.05;
    text-shadow: 0 4px 24px rgba(0,0,0,0.5);
}
.hero .accent { color: var(--accent); }
.hero p {
    color: rgba(230, 236, 255, 0.92);
    margin: 0 auto;
    font-size: 1.15rem;
    font-weight: 500;
    max-width: 760px;
    line-height: 1.5;
    text-shadow: 0 2px 12px rgba(0,0,0,0.6);
}
.hero p .pill {
    display: inline-block;
    background: rgba(74,144,255,0.18);
    color: var(--accent);
    border: 1px solid rgba(74,144,255,0.35);
    padding: 0.1rem 0.55rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin: 0 0.15rem;
    vertical-align: middle;
}
.hero-search-wrap { max-width: 640px; margin: 2rem auto 0.5rem; }
.hero-search-wrap .champ-search {
    background: rgba(7,11,24,0.78);
    border: 1px solid rgba(74,144,255,0.25);
    border-radius: 12px;
    box-shadow: 0 8px 32px rgba(7,11,24,0.6);
}
.hero-search-wrap .champ-search input {
    padding: 0.95rem 1.15rem;
    font-size: 1.02rem;
}
.hero-search-wrap .champ-search button {
    padding: 0 1.75rem;
    font-size: 1rem;
}

/* --- Generic card --- Modern glass-morphic surface ---
   Translucent dark with a backdrop blur, hairline border, and a soft
   accent stripe across the top edge. Hovering lifts the card 2px and
   strengthens the accent border. */
.wr-card {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.025) 0%, transparent 100%),
        rgba(12, 18, 38, 0.62);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    height: 100%;
    backdrop-filter: blur(14px) saturate(120%);
    -webkit-backdrop-filter: blur(14px) saturate(120%);
    position: relative;
    overflow: hidden;
    transition: border-color 0.25s, transform 0.25s, box-shadow 0.25s;
    box-shadow: 0 4px 24px rgba(0,0,0,0.25);
}
.wr-card::before {
    content: '';
    position: absolute;
    top: 0; left: 12%; right: 12%; height: 1px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(74,144,255,0.55) 50%, transparent 100%);
    opacity: 0.75;
}
.wr-card:hover {
    border-color: rgba(74, 144, 255, 0.22);
    transform: translateY(-2px);
    box-shadow: 0 10px 32px rgba(0,0,0,0.4);
}
.wr-card-header {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 1rem;
}
.wr-card-title {
    font-size: 0.78rem; font-weight: 700;
    letter-spacing: 0.14em; text-transform: uppercase;
    color: var(--text);
    margin: 0;
}
.wr-card-link {
    color: var(--accent); font-size: 0.78rem; text-decoration: none;
    font-weight: 600; letter-spacing: 0.04em;
    transition: opacity 0.15s;
}
.wr-card-link:hover { opacity: 0.7; }

/* --- Season-in-progress card --- */
.season-card {
    background: linear-gradient(135deg, #121a30 0%, #1a2342 100%);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    padding: 1.75rem 2rem;
    display: grid;
    /* Narrower feature column so Kai'Sa's face shows in the gap. */
    grid-template-columns: minmax(0, 1fr) 280px;
    gap: 2rem; align-items: center;
    margin: 1.5rem 0;
    box-shadow: 0 6px 28px rgba(0,0,0,0.35);
    position: relative;
    overflow: hidden;
}
.season-card::before {
    content: '';
    position: absolute;
    top: 0; left: 30%; right: 30%; height: 1px;
    z-index: 3;
    background: linear-gradient(90deg,
        transparent, rgba(74,144,255,0.5), transparent);
}
/* Animated Kai'Sa layer — sits behind the gradient + content and drifts
   with a slow Ken-Burns zoom/pan so the landing card feels alive without
   being distracting. The negative inset gives the transform room so the
   card edges never expose a gap. */
.season-card-bg {
    position: absolute;
    inset: -8%;
    z-index: 0;
    background-size: cover;
    background-repeat: no-repeat;
    background-position: 62% 6%;
    will-change: transform;
    animation: season-kenburns 34s ease-in-out infinite;
}
@keyframes season-kenburns {
    0%   { transform: scale(1.0)  translate(0, 0); }
    50%  { transform: scale(1.065) translate(-1.6%, 1.5%); }
    100% { transform: scale(1.0)  translate(0, 0); }
}
/* Gradient overlay above the image, below the content, for text legibility. */
.season-card-overlay {
    position: absolute;
    inset: 0;
    z-index: 1;
    pointer-events: none;
    background: linear-gradient(95deg,
        rgba(12,18,38,0.95) 0%, rgba(12,18,38,0.55) 45%, rgba(18,26,48,0.2) 85%);
}
/* Real content rides above both layers. */
.season-card > div:not(.season-card-bg):not(.season-card-overlay) {
    position: relative;
    z-index: 2;
}
@media (prefers-reduced-motion: reduce) {
    .season-card-bg { animation: none; }
}
@media (max-width: 900px) {
    .season-card { grid-template-columns: 1fr; }
}
.season-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; background: var(--accent);
    margin-right: 0.5rem; box-shadow: 0 0 8px var(--accent);
}
.season-label {
    color: var(--accent); font-size: 0.75rem;
    letter-spacing: 0.12em; text-transform: uppercase; font-weight: 700;
}
.season-row { display: flex; gap: 1.5rem; align-items: center; margin-top: 0.75rem; }
.season-emblem {
    width: 96px; height: 96px;
    background: radial-gradient(circle, rgba(74,144,255,0.25), transparent 70%);
    display: flex; align-items: center; justify-content: center;
    font-size: 3rem;
}
.season-number { font-size: 3.5rem; font-weight: 800; line-height: 1; }
.season-tag { color: var(--muted); font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; }
.season-title { font-size: 1.4rem; font-weight: 700; }
.progress-bar {
    height: 6px; background: rgba(255,255,255,0.06);
    border-radius: 3px; overflow: hidden;
    margin: 1.25rem 0 0.5rem;
}
.progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent), #7aaaff); }
.season-meta { color: var(--muted); font-size: 0.85rem; }
.season-meta strong { color: var(--text); }

.season-feature {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.04) 0%, transparent 100%),
        rgba(8, 12, 28, 0.72);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 0.8rem 1rem;
    display: flex; align-items: center; gap: 0.8rem;
    backdrop-filter: blur(10px) saturate(120%);
    -webkit-backdrop-filter: blur(10px) saturate(120%);
    transition: border-color 0.2s, transform 0.2s;
}
.season-feature:hover {
    border-color: rgba(74,144,255,0.25);
    transform: translateY(-1px);
}
.feature-tag {
    background: var(--accent-dim); color: white;
    font-size: 0.6rem; padding: 0.22rem 0.5rem;
    border-radius: 4px; font-weight: 700; letter-spacing: 0.05em;
    white-space: nowrap;
}
.feature-tag.green { background: var(--green); }
.feature-name { font-weight: 700; letter-spacing: 0.03em; font-size: 0.92rem; }
.feature-sub { color: var(--muted); font-size: 0.78rem; }
.feature-avatar {
    width: 40px; height: 40px; border-radius: 50%;
    background: linear-gradient(135deg, var(--card-2), var(--accent-dim));
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.9rem;
    flex-shrink: 0;
    overflow: hidden;
}

/* --- Row table style (top-champions + top-leaderboard previews) --- */
.row-list { display: flex; flex-direction: column; gap: 0.1rem; }
.row {
    display: grid; grid-template-columns: 44px 40px 1fr auto auto;
    align-items: center; gap: 1rem; padding: 0.7rem 0.6rem;
    border-radius: 8px;
    transition: background 0.18s, transform 0.18s;
}
.row + .row { border-top: 1px solid rgba(255,255,255,0.04); }
.row:hover {
    background: rgba(74,144,255,0.05);
}
.row .rank { color: var(--muted); font-weight: 600; font-size: 0.95rem; text-align: center; }

/* Top-3 rank styling — gradient-filled big numbers with a soft glow */
.row .rank.r-1, .row .rank.r-2, .row .rank.r-3 {
    font-size: 1.5rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    filter: drop-shadow(0 0 8px rgba(212,166,74,0.35));
}
.row .rank.r-1 { background-image: linear-gradient(135deg, var(--gold-bright), var(--gold)); }
.row .rank.r-2 {
    background-image: linear-gradient(135deg, #e6edff, var(--silver));
    filter: drop-shadow(0 0 8px rgba(201,208,224,0.35));
}
.row .rank.r-3 {
    background-image: linear-gradient(135deg, #f0a36a, var(--bronze));
    filter: drop-shadow(0 0 8px rgba(205,136,74,0.35));
}

.row .avatar {
    width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, var(--card-2), var(--accent-dim));
    display: flex; align-items: center; justify-content: center;
    font-weight: 700; font-size: 0.85rem; color: var(--text);
    overflow: hidden; flex-shrink: 0;
}
.row .avatar img,
.feature-avatar img {
    width: 100%; height: 100%;
    object-fit: cover; border-radius: 50%;
    display: block;
}
.row .avatar.ring-gold {
    box-shadow: 0 0 0 2px var(--gold), 0 0 12px rgba(212,166,74,0.55);
}
.row .avatar.ring-silver {
    box-shadow: 0 0 0 2px var(--silver), 0 0 12px rgba(201,208,224,0.45);
}
.row .avatar.ring-bronze {
    box-shadow: 0 0 0 2px var(--bronze), 0 0 12px rgba(205,136,74,0.45);
}
.row .name { font-weight: 500; }
.row.r-top .name { font-weight: 700; }
.row .badge {
    display: inline-block; padding: 0.1rem 0.5rem;
    background: var(--accent); color: white;
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.05em;
    border-radius: 4px; margin-left: 0.5rem; vertical-align: middle;
}
.row .wr { color: var(--accent); font-weight: 700; min-width: 90px; text-align: right; }
.row .pick { color: var(--muted); font-size: 0.9rem; min-width: 80px; text-align: right; }
.row .score { color: var(--text); font-weight: 700; min-width: 80px; text-align: right; }
.row .score::before { content: "◆ "; color: var(--accent); }

/* --- Leaderboard splash card with Ken-Burns bg + stats overlay --- */
.splash-card {
    width: 100%;
    aspect-ratio: 308 / 560;
    border-radius: 14px;
    border: 1px solid var(--border);
    overflow: hidden;
    position: relative;
    background-color: var(--card);
    box-shadow: 0 8px 28px rgba(0,0,0,0.4);
}
/* Animated background lives in its own div so the stats overlay
   sits still while the art slowly drifts. */
.splash-card-bg {
    position: absolute;
    /* Negative inset gives the scale/translate keyframes some room
       so we never see the underlying card color at the edges. */
    inset: -8%;
    background-size: cover;
    background-position: center 18%;
    animation: kenburns 22s ease-in-out infinite;
    z-index: 0;
}
@keyframes kenburns {
    0%   { transform: scale(1.0)  translate(0, 0); }
    40%  { transform: scale(1.08) translate(-2%, -2.5%); }
    70%  { transform: scale(1.05) translate(2%, -1%); }
    100% { transform: scale(1.0)  translate(0, 0); }
}
/* All overlays sit above the animated bg. Children already declare their
   own `position: absolute`; we MUST NOT overwrite that here, only stack
   them above the bg via z-index. */
.splash-card > *:not(.splash-card-bg) { z-index: 1; }

.splash-card-eyebrow {
    position: absolute;
    top: 1rem; left: 1.1rem; right: 1.1rem;
    color: var(--accent);
    font-size: 0.7rem;
    font-weight: 800;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    text-shadow: 0 2px 8px rgba(0,0,0,0.9);
}
.splash-card-name {
    position: absolute;
    top: 2.1rem; left: 1.1rem; right: 1.1rem;
    color: white;
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    line-height: 1.1;
    text-shadow: 0 2px 14px rgba(0,0,0,0.9);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.splash-card-sub {
    position: absolute;
    top: 3.85rem; left: 1.1rem; right: 1.1rem;
    color: rgba(255,255,255,0.85);
    font-size: 0.85rem;
    font-weight: 500;
    text-shadow: 0 2px 10px rgba(0,0,0,0.85);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.splash-stats {
    position: absolute;
    left: 0; right: 0; bottom: 0;
    padding: 2.5rem 1.1rem 1.1rem;
    background: linear-gradient(to top,
        rgba(7,11,24,0.96) 0%,
        rgba(7,11,24,0.86) 55%,
        rgba(7,11,24,0.3) 88%,
        transparent 100%);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
}
.stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.85rem 1rem;
}
.stat-label {
    color: var(--muted);
    font-size: 0.62rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 700;
    margin-bottom: 0.15rem;
}
.stat-value {
    color: var(--text);
    font-weight: 800;
    font-size: 1.35rem;
    line-height: 1.05;
    letter-spacing: -0.01em;
}
.stat-value.accent { color: var(--accent); }
.stat-value.gold { color: var(--gold-bright); }
.stat-value.tier-god { color: #ff7a3c; }
.stat-value.tier-s { color: #ff8c42; }
.stat-value.tier-a { color: #ffd14a; }
.stat-value.tier-b { color: #4a90ff; }
.stat-value.tier-c { color: #8a92a8; }
.stat-value.tier-ass { color: #6a7088; }
.stat-value.tier-unknown { color: var(--muted); }

/* --- Tier list rows --- */
.tier-row {
    display: flex;
    gap: 0.85rem;
    margin-bottom: 0.85rem;
    align-items: stretch;
    min-height: 118px;
}
.tier-label {
    flex-shrink: 0;
    width: 110px;
    background: var(--card);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 2.5rem;
    font-weight: 900;
    letter-spacing: -0.04em;
    box-shadow: 0 4px 18px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.08);
    position: relative;
    overflow: hidden;
}
.tier-label::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, rgba(255,255,255,0.12) 0%, transparent 50%);
    pointer-events: none;
}
.tier-label.tier-god {
    background: linear-gradient(135deg, #ffd24a 0%, #ff7a1a 45%, #e53916 100%);
    color: #fff; border-color: rgba(255,120,40,0.6);
    font-size: 1.7rem;
    box-shadow: 0 4px 18px rgba(229,57,22,0.5), inset 0 1px 0 rgba(255,255,255,0.25),
                0 0 24px rgba(255,120,40,0.45);
    animation: god-pulse 2.6s ease-in-out infinite;
}
@keyframes god-pulse {
    0%, 100% { box-shadow: 0 4px 18px rgba(229,57,22,0.5), inset 0 1px 0 rgba(255,255,255,0.25), 0 0 22px rgba(255,120,40,0.4); }
    50%      { box-shadow: 0 4px 22px rgba(229,57,22,0.7), inset 0 1px 0 rgba(255,255,255,0.3),  0 0 36px rgba(255,140,50,0.65); }
}
.tier-label.tier-s      { background: linear-gradient(135deg, #ff8c42, #ff6b1a); color: white; border-color: rgba(255,140,66,0.5); }
.tier-label.tier-a      { background: linear-gradient(135deg, #ffd14a, #f5b800); color: #2a1500; border-color: rgba(255,209,74,0.5); }
.tier-label.tier-b      { background: linear-gradient(135deg, #4a90ff, #2b6ad6); color: white; border-color: rgba(74,144,255,0.5); }
.tier-label.tier-c      { background: linear-gradient(135deg, #8a92a8, #5a6378); color: white; border-color: rgba(138,146,168,0.5); }
.tier-label.tier-ass {
    background: linear-gradient(135deg, #4a5066 0%, #353a4d 60%, #2a2e3e 100%);
    color: #aeb4c6; border-color: rgba(106,112,136,0.4);
    font-size: 1.9rem;
    filter: saturate(0.6);
}

.tier-champs {
    flex: 1;
    background:
        linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 100%),
        rgba(12, 18, 38, 0.55);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 1rem 1.1rem;
    display: flex;
    flex-wrap: wrap;
    gap: 0.9rem;
    align-items: center;
    backdrop-filter: blur(14px) saturate(120%);
    -webkit-backdrop-filter: blur(14px) saturate(120%);
}
.tier-champ {
    width: 64px;
    text-align: center;
    transition: transform 0.18s;
    cursor: default;
}
.tier-champ:hover { transform: translateY(-3px); }
.tier-champ img {
    width: 56px;
    height: 56px;
    border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.08);
    object-fit: cover;
    display: block;
    margin: 0 auto;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    transition: border-color 0.18s, box-shadow 0.18s;
}
.tier-champ:hover img {
    border-color: rgba(74,144,255,0.45);
    box-shadow: 0 4px 16px rgba(74,144,255,0.4);
}
.tier-champ .champ-name {
    font-size: 0.72rem;
    color: var(--text);
    margin-top: 0.3rem;
    font-weight: 500;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.tier-champ .champ-wr {
    font-size: 0.7rem;
    color: var(--accent);
    font-weight: 700;
}
.tier-empty {
    color: var(--muted);
    font-style: italic;
    font-size: 0.9rem;
}

/* --- Insights grid (landing page sub-cards) --- */
.insights-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1rem;
    margin: 1.5rem 0;
}
@media (max-width: 900px) { .insights-grid { grid-template-columns: 1fr; } }

.insight-card {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.025) 0%, transparent 100%),
        rgba(12, 18, 38, 0.55);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    padding: 1.2rem 1.35rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    backdrop-filter: blur(14px) saturate(120%);
    -webkit-backdrop-filter: blur(14px) saturate(120%);
    position: relative;
    overflow: hidden;
    transition: border-color 0.25s, transform 0.25s;
    box-shadow: 0 4px 20px rgba(0,0,0,0.22);
}
.insight-card::before {
    content: '';
    position: absolute;
    top: 0; left: 18%; right: 18%; height: 1px;
    background: linear-gradient(90deg,
        transparent, rgba(74,144,255,0.45), transparent);
}
.insight-card:hover {
    border-color: rgba(74,144,255,0.22);
    transform: translateY(-2px);
}
.insight-card-title {
    color: var(--text);
    font-size: 0.72rem;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    font-weight: 700;
    margin-bottom: 0.4rem;
    display: flex; justify-content: space-between; align-items: center;
}
.insight-card-title .accent { color: var(--accent); }

.insight-row {
    display: grid;
    grid-template-columns: 28px 36px 1fr auto;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem 0.4rem;
    border-radius: 6px;
    transition: background 0.18s;
}
.insight-row + .insight-row { border-top: 1px solid rgba(255,255,255,0.04); }
.insight-row:hover { background: rgba(74,144,255,0.05); }

/* Variant used by the Funniest Names card — no rank or metric cell, just
   icon + name. Champion icon hints which champ they were spotted on. */
.insight-card.funny .insight-row {
    grid-template-columns: 36px 1fr;
}

/* ---- "View more" expander on insight cards ---- */
.insight-more {
    margin-top: 0.5rem;
    border-top: 1px solid rgba(255,255,255,0.06);
    padding-top: 0.4rem;
}
.insight-more summary {
    cursor: pointer; user-select: none;
    color: var(--accent);
    font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.14em; text-transform: uppercase;
    padding: 0.35rem 0.4rem;
    border-radius: 6px;
    list-style: none;
    transition: background 0.15s, color 0.15s;
    text-align: center;
}
.insight-more summary::-webkit-details-marker { display: none; }
.insight-more summary::after {
    content: " \\25BE";   /* ▾ */
    color: var(--muted);
    font-size: 0.65rem;
    margin-left: 0.3rem;
    transition: transform 0.2s;
    display: inline-block;
}
.insight-more[open] summary::after { content: " \\25B4"; }   /* ▴ */
.insight-more summary:hover {
    color: #5fa0ff;
    background: rgba(74,144,255,0.06);
}
.insight-extra { margin-top: 0.25rem; }
.insight-extra .insight-row { padding: 0.4rem 0.4rem; }
.insight-row .rank {
    font-weight: 800;
    font-size: 0.95rem;
    text-align: center;
    color: var(--muted);
}
.insight-row .rank.r-1 {
    color: transparent;
    background: linear-gradient(135deg, var(--gold-bright), var(--gold));
    -webkit-background-clip: text; background-clip: text;
}
.insight-row .rank.r-2 {
    color: transparent;
    background: linear-gradient(135deg, #e6edff, var(--silver));
    -webkit-background-clip: text; background-clip: text;
}
.insight-row .rank.r-3 {
    color: transparent;
    background: linear-gradient(135deg, #f0a36a, var(--bronze));
    -webkit-background-clip: text; background-clip: text;
}
.insight-row .icon img {
    width: 30px; height: 30px; border-radius: 50%;
    object-fit: cover; display: block;
}
.insight-row .name {
    font-weight: 600; font-size: 0.92rem;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.insight-row .metric {
    color: var(--accent);
    font-weight: 700;
    font-size: 0.92rem;
    text-align: right;
}
.insight-row .metric.muted { color: var(--muted); }
.insight-row .metric.down  { color: #ff8c8c; }
.insight-row .metric.gold  { color: var(--gold-bright); }

/* "Pick of the patch" wide hero card — glass + accent edge */
.pick-patch-card {
    background:
        linear-gradient(135deg, rgba(74,144,255,0.14) 0%, rgba(212,166,74,0.06) 100%),
        linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 100%),
        rgba(12, 18, 38, 0.55);
    border: 1px solid rgba(74,144,255,0.22);
    border-radius: 16px;
    padding: 1.6rem 1.8rem;
    display: grid;
    grid-template-columns: 100px 1fr auto;
    align-items: center;
    gap: 1.5rem;
    margin: 1.5rem 0;
    backdrop-filter: blur(16px) saturate(125%);
    -webkit-backdrop-filter: blur(16px) saturate(125%);
    position: relative;
    overflow: hidden;
    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.pick-patch-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg,
        transparent 0%, rgba(74,144,255,0.6) 30%, rgba(212,166,74,0.5) 70%, transparent 100%);
}
.pick-patch-card .pp-icon img {
    width: 88px; height: 88px;
    border-radius: 50%;
    object-fit: cover;
    border: 3px solid var(--accent);
    box-shadow: 0 0 20px rgba(74,144,255,0.5);
}
.pick-patch-card .pp-title {
    color: var(--accent);
    font-size: 0.78rem; font-weight: 800;
    letter-spacing: 0.16em; text-transform: uppercase;
    margin-bottom: 0.25rem;
}
.pick-patch-card .pp-name {
    font-size: 1.8rem; font-weight: 800;
    letter-spacing: -0.01em;
    margin-bottom: 0.2rem;
}
.pick-patch-card .pp-meta {
    color: var(--muted);
    font-size: 0.9rem;
}
.pick-patch-card .pp-stats {
    display: flex; flex-direction: column; gap: 0.3rem; align-items: flex-end;
}
.pick-patch-card .pp-wr {
    font-size: 1.85rem; font-weight: 800;
    color: var(--accent);
    line-height: 1;
}
.pick-patch-card .pp-wr-label {
    color: var(--muted);
    font-size: 0.7rem; letter-spacing: 0.12em;
    text-transform: uppercase; font-weight: 700;
}

/* Role-average WR card */
.role-wr-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 0.6rem;
}
@media (max-width: 700px) { .role-wr-grid { grid-template-columns: repeat(2, 1fr); } }
.role-wr-cell {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 100%),
        rgba(7, 11, 24, 0.45);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px;
    padding: 0.85rem 0.6rem;
    text-align: center;
    transition: border-color 0.2s, transform 0.2s;
}
.role-wr-cell:hover {
    border-color: rgba(74,144,255,0.25);
    transform: translateY(-2px);
}
.role-wr-cell .role-name {
    color: var(--muted);
    font-size: 0.68rem; letter-spacing: 0.14em;
    text-transform: uppercase; font-weight: 700;
    margin-bottom: 0.4rem;
}
.role-wr-cell .role-wr {
    font-size: 1.4rem; font-weight: 800;
    color: var(--accent);
    line-height: 1.05;
}
.role-wr-cell .role-wr.empty {
    color: var(--muted);
    font-size: 1rem;
    font-weight: 600;
}
.role-wr-cell .role-wr.low-conf {
    color: #8a92a8;   /* dimmed — number exists but is backed by few champions */
}
.role-wr-cell .role-flag {
    color: var(--gold);
    font-size: 0.8rem;
    cursor: help;
}
.role-wr-cell .role-sub {
    color: var(--muted);
    font-size: 0.62rem;
    font-weight: 600;
    margin-top: 0.25rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
}
.role-wr-cell .role-sub-label { letter-spacing: 0.1em; }
/* The "whole pool" secondary number, smaller and quieter than the meta WR. */
.role-wr-cell .role-pool {
    margin-top: 0.55rem;
    padding-top: 0.5rem;
    border-top: 1px dashed rgba(255,255,255,0.08);
    display: flex; flex-direction: column; gap: 0.1rem;
}
.role-wr-cell .role-pool-wr {
    color: var(--text);
    font-size: 0.92rem;
    font-weight: 700;
}
.role-wr-cell .role-pool-label {
    color: var(--muted);
    font-size: 0.6rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

/* Four at-a-glance stat widgets (landing, above the season card) */
.stat-widgets {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
    margin: 0.5rem 0 1.5rem;
}
@media (max-width: 820px) { .stat-widgets { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 440px) { .stat-widgets { grid-template-columns: 1fr; } }
.stat-widget {
    background:
        linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 100%),
        rgba(12, 18, 38, 0.6);
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    backdrop-filter: blur(14px) saturate(120%);
    -webkit-backdrop-filter: blur(14px) saturate(120%);
    position: relative;
    overflow: hidden;
    transition: border-color 0.25s, transform 0.25s;
    box-shadow: 0 4px 18px rgba(0,0,0,0.22);
    display: flex; align-items: center; justify-content: space-between; gap: 0.75rem;
    min-height: 92px;
}
.stat-widget::before {
    content: '';
    position: absolute;
    top: 0; left: 14%; right: 14%; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(74,144,255,0.5), transparent);
}
.stat-widget:hover { border-color: rgba(74,144,255,0.22); transform: translateY(-2px); }
.sw-left { min-width: 0; flex: 1; }
.sw-right { flex-shrink: 0; text-align: right; }
.sw-eyebrow {
    color: var(--muted);
    font-size: 0.64rem; letter-spacing: 0.14em;
    text-transform: uppercase; font-weight: 700;
    margin-bottom: 0.5rem;
}
.sw-main { display: flex; align-items: center; gap: 0.5rem; min-width: 0; }
.sw-icon {
    width: 38px; height: 38px; border-radius: 50%;
    object-fit: cover; flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.12);
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
.sw-big {
    font-size: 1.4rem; font-weight: 800; letter-spacing: -0.01em;
    color: var(--text);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.sw-big.accent { color: var(--accent); }
.sw-sub {
    color: var(--muted); font-size: 0.74rem; font-weight: 600;
    margin-top: 0.4rem; letter-spacing: 0.04em; text-transform: uppercase;
}
.sw-pct {
    font-size: 2rem; font-weight: 800; line-height: 1;
    letter-spacing: -0.02em; color: var(--accent);
}
.sw-pct.down { color: #ff8c8c; }
.sw-pct.gold { color: var(--gold-bright); }

/* ---- Spotlight / featured champion card (landing) ---- */
.spotlight-card {
    position: relative;
    border-radius: 16px;
    overflow: hidden;
    margin: 1.25rem 0 1.5rem;
    border: 1px solid rgba(255,255,255,0.08);
    box-shadow: 0 10px 40px rgba(0,0,0,0.35);
    min-height: 260px;
    isolation: isolate;
}
.spotlight-card-bg {
    position: absolute; inset: -6%;
    background-size: cover;
    background-position: 75% 22%;
    z-index: 0;
    animation: spotlight-drift 28s ease-in-out infinite;
}
@keyframes spotlight-drift {
    0%   { transform: scale(1.0) translate(0, 0); }
    50%  { transform: scale(1.05) translate(-1.2%, -1%); }
    100% { transform: scale(1.0) translate(0, 0); }
}
@media (prefers-reduced-motion: reduce) {
    .spotlight-card-bg { animation: none; }
}
.spotlight-card-overlay {
    position: absolute; inset: 0; z-index: 1; pointer-events: none;
    background: linear-gradient(95deg,
        rgba(7,11,24,0.95) 0%,
        rgba(7,11,24,0.78) 38%,
        rgba(7,11,24,0.35) 70%,
        rgba(7,11,24,0.05) 100%);
}
.spotlight-content {
    position: relative; z-index: 2;
    padding: 1.6rem 1.8rem;
    display: grid;
    grid-template-columns: 1fr;
    gap: 1.1rem;
}
.spotlight-eyebrow {
    color: var(--accent);
    font-size: 0.7rem; font-weight: 800;
    letter-spacing: 0.18em; text-transform: uppercase;
    display: inline-flex; align-items: center; gap: 0.5rem;
}
.spotlight-eyebrow::before {
    content: ''; width: 7px; height: 7px; border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 10px var(--accent);
    animation: pulse-dot 1.8s ease-in-out infinite;
}
@keyframes pulse-dot {
    0%, 100% { opacity: 0.55; }
    50% { opacity: 1; }
}
.spotlight-headline {
    display: flex; align-items: baseline; flex-wrap: wrap; gap: 1rem;
}
.spotlight-name {
    font-size: 3rem; font-weight: 800; letter-spacing: -0.02em; line-height: 1;
    text-shadow: 0 4px 18px rgba(0,0,0,0.7);
}
.spotlight-tags {
    display: flex; gap: 0.5rem; flex-wrap: wrap; align-items: center;
    color: rgba(230,236,255,0.85); font-size: 0.85rem; font-weight: 600;
}
.spotlight-tags .sep { color: var(--muted); }

.spotlight-stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
    max-width: 720px;
}
@media (max-width: 720px) {
    .spotlight-stats { grid-template-columns: repeat(2, 1fr); }
    .spotlight-name { font-size: 2.2rem; }
}
.sl-stat {
    background: rgba(7, 11, 24, 0.55);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 0.7rem 0.85rem;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
}
.sl-stat-label {
    color: var(--muted);
    font-size: 0.62rem; letter-spacing: 0.14em;
    text-transform: uppercase; font-weight: 700;
    margin-bottom: 0.3rem;
}
.sl-stat-value {
    font-size: 1.5rem; font-weight: 800; letter-spacing: -0.01em;
    color: var(--text); line-height: 1;
}
.sl-stat-value.accent { color: var(--accent); }
.sl-stat-value.gold   { color: var(--gold-bright); }
.sl-stat-value.tier-god { color: #ff7a3c; }
.sl-stat-value.tier-s   { color: #ff8c42; }
.sl-stat-value.tier-a   { color: #ffd14a; }
.sl-stat-value.tier-b   { color: #4a90ff; }
.sl-stat-value.tier-c   { color: #8a92a8; }
.sl-stat-value.tier-ass { color: #6a7088; }

.sl-chart-card {
    background: rgba(7, 11, 24, 0.55);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 0.7rem 0.9rem 0.85rem;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    max-width: 720px;
}
.sl-chart-head {
    display: flex; align-items: baseline; justify-content: space-between;
    margin-bottom: 0.45rem;
    flex-wrap: wrap; gap: 0.5rem;
}
.sl-chart-title {
    color: var(--muted);
    font-size: 0.62rem; letter-spacing: 0.14em;
    text-transform: uppercase; font-weight: 700;
}
.sl-chart-meta {
    color: rgba(230,236,255,0.85);
    font-size: 0.78rem; font-weight: 600;
}
.sl-chart-meta .accent { color: var(--accent); }

.spotlight-bestplayer {
    color: rgba(230,236,255,0.9);
    font-size: 0.9rem;
    margin-top: 0.35rem;
}
.spotlight-bestplayer strong { color: var(--gold-bright); font-weight: 700; }
.spotlight-bestplayer .muted { color: var(--muted); }

/* Meta breakdown (win rate by class, horizontal bars) */
.meta-grid { display: flex; flex-direction: column; gap: 0.55rem; }
.meta-row {
    display: grid;
    grid-template-columns: 96px 1fr 56px 78px;
    align-items: center;
    gap: 0.85rem;
}
.meta-class {
    color: var(--text);
    font-size: 0.85rem; font-weight: 700;
    letter-spacing: 0.02em;
}
.meta-flag { color: var(--gold); font-size: 0.75rem; cursor: help; }
.meta-bar {
    height: 10px;
    background: rgba(255,255,255,0.05);
    border-radius: 999px;
    overflow: hidden;
}
.meta-bar-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, rgba(74,144,255,0.5), var(--accent));
    transition: width 0.4s;
}
.meta-bar-fill.head {
    background: linear-gradient(90deg, #ff8c42, #ffd14a);
    box-shadow: 0 0 12px rgba(255,160,60,0.5);
}
.meta-wr { color: var(--accent); font-weight: 800; font-size: 0.92rem; text-align: right; }
.meta-n { color: var(--muted); font-size: 0.72rem; text-align: right; }
@media (max-width: 600px) {
    .meta-row { grid-template-columns: 72px 1fr 48px; }
    .meta-n { display: none; }
}

/* Stub "Coming soon" card for the queue/mode panels */
.stub-card {
    background:
        linear-gradient(135deg, rgba(74,144,255,0.06), transparent),
        var(--card);
    border: 1px dashed rgba(74,144,255,0.3);
    border-radius: 12px;
    padding: 1.25rem 1.4rem;
    color: var(--muted);
    font-size: 0.92rem;
}
.stub-card .stub-eyebrow {
    color: var(--accent);
    font-size: 0.72rem; letter-spacing: 0.14em;
    text-transform: uppercase; font-weight: 700;
    margin-bottom: 0.4rem;
}
.stub-card .stub-title {
    color: var(--text);
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 0.4rem;
}

/* --- Custom data table (replaces st.dataframe) --- */
.wr-table-wrap {
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    overflow: hidden;
    background:
        linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 100%),
        rgba(12, 18, 38, 0.55);
    backdrop-filter: blur(14px) saturate(120%);
    -webkit-backdrop-filter: blur(14px) saturate(120%);
    box-shadow: 0 6px 24px rgba(0,0,0,0.25);
}
.wr-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
/* Scrollable variant — fixed height shows ~5 rows, scroll for the rest.
   Header stays pinned via sticky positioning. */
.wr-table-scroll {
    max-height: 322px;
    overflow-y: auto;
}
.wr-table-scroll thead th {
    position: sticky; top: 0; z-index: 2;
    background: #0f1426;
}
.wr-table-scroll::-webkit-scrollbar { width: 8px; }
.wr-table-scroll::-webkit-scrollbar-thumb {
    background: rgba(74,144,255,0.3); border-radius: 4px;
}
.wr-table-scroll::-webkit-scrollbar-track { background: transparent; }
.wr-table thead th {
    color: var(--muted);
    font-weight: 600; font-size: 0.7rem;
    letter-spacing: 0.12em; text-transform: uppercase;
    text-align: left;
    padding: 0.85rem 0.9rem;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    white-space: nowrap;
}
.wr-table thead th.num { text-align: right; }
.wr-table thead th.center { text-align: center; }
.wr-table tbody td {
    padding: 0.6rem 0.9rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    vertical-align: middle;
}
.wr-table tbody td.num { text-align: right; font-variant-numeric: tabular-nums; }
.wr-table tbody td.center { text-align: center; }
.wr-table tbody tr:last-child td { border-bottom: none; }
.wr-table tbody tr { transition: background 0.15s; }
.wr-table tbody tr:hover { background: rgba(74,144,255,0.06); }
.wr-table tbody tr.r-top1 td { background: rgba(212,166,74,0.08); }
.wr-table tbody tr.r-top2 td { background: rgba(201,208,224,0.05); }
.wr-table tbody tr.r-top3 td { background: rgba(205,136,74,0.06); }

.wr-table .cell-champ { display: flex; align-items: center; gap: 0.6rem; }
.wr-table .cell-champ img {
    width: 30px; height: 30px; border-radius: 50%;
    object-fit: cover; flex-shrink: 0;
    border: 1px solid rgba(255,255,255,0.08);
}
.wr-table .cell-champ .cn { font-weight: 600; }
.wr-table .cell-rank {
    font-weight: 800; color: var(--muted); text-align: center;
}
.wr-table tr.r-top1 .cell-rank { color: var(--gold-bright); }
.wr-table tr.r-top2 .cell-rank { color: var(--silver); }
.wr-table tr.r-top3 .cell-rank { color: var(--bronze); }

/* ---- OTP (One-Trick-Pony) badges ----
   `otp-badge-inline` sits next to a number in tables/lists; `otp-badge`
   floats top-right of a tier-list icon. */
.otp-badge-inline {
    display: inline-block;
    margin-left: 0.45rem;
    padding: 0.06rem 0.4rem;
    background: linear-gradient(135deg, #ff8c42, #e2531a);
    color: #fff;
    font-size: 0.62rem; font-weight: 800;
    letter-spacing: 0.08em;
    border-radius: 5px;
    box-shadow: 0 0 0 1px rgba(0,0,0,0.4), 0 0 6px rgba(255,140,66,0.45);
    vertical-align: middle;
}
.tier-champ-icon { position: relative; width: 56px; height: 56px; margin: 0 auto; }
.tier-champ-icon img {
    /* override the standalone .tier-champ img rule when wrapped */
    margin: 0 !important;
}
/* Red border on Hard / Very Hard champions — signals "advanced players only". */
.tier-champ-icon.diff-hard img {
    border: 2px solid #ff5a5a !important;
    box-shadow: 0 0 6px rgba(255,90,90,0.45);
}
.tier-champ-icon .otp-badge {
    position: absolute;
    top: -4px; right: -6px;
    padding: 1px 4px;
    background: linear-gradient(135deg, #ff8c42, #e2531a);
    color: #fff;
    font-size: 0.56rem; font-weight: 900;
    letter-spacing: 0.05em;
    border-radius: 4px;
    border: 1px solid rgba(0,0,0,0.45);
    box-shadow: 0 0 8px rgba(255,140,66,0.55);
    z-index: 2;
    cursor: help;
}

/* tier pill inside a table cell */
.tier-pill {
    display: inline-block; min-width: 36px; text-align: center;
    padding: 0.12rem 0.5rem; border-radius: 6px;
    font-weight: 800; font-size: 0.78rem;
}
.tier-pill.tier-god { background: linear-gradient(135deg,#ffd24a,#e53916); color:#fff; }
.tier-pill.tier-s   { background: linear-gradient(135deg,#ff8c42,#ff6b1a); color:#fff; }
.tier-pill.tier-a   { background: linear-gradient(135deg,#ffd14a,#f5b800); color:#2a1500; }
.tier-pill.tier-b   { background: linear-gradient(135deg,#4a90ff,#2b6ad6); color:#fff; }
.tier-pill.tier-c   { background: linear-gradient(135deg,#8a92a8,#5a6378); color:#fff; }
.tier-pill.tier-ass { background: linear-gradient(135deg,#4a5066,#2a2e3e); color:#aeb4c6; }

/* class chip */
.class-chip {
    display: inline-block; padding: 0.12rem 0.55rem;
    border-radius: 999px; font-size: 0.74rem; font-weight: 700;
    border: 1px solid rgba(255,255,255,0.12);
    color: var(--text);
}
.class-chip.Tank      { background: rgba(74,144,255,0.14); border-color: rgba(74,144,255,0.4); }
.class-chip.Bruiser   { background: rgba(229,90,40,0.14);  border-color: rgba(229,90,40,0.4); }
.class-chip.Assassin  { background: rgba(220,40,80,0.14);  border-color: rgba(220,40,80,0.4); }
.class-chip.Mage      { background: rgba(150,90,255,0.14); border-color: rgba(150,90,255,0.4); }
.class-chip.Marksman  { background: rgba(255,200,60,0.14); border-color: rgba(255,200,60,0.4); }
.class-chip.Enchanter { background: rgba(60,200,140,0.14); border-color: rgba(60,200,140,0.4); }

/* difficulty dots */
.diff-dots { display: inline-flex; gap: 3px; align-items: center; }
.diff-dot { width: 7px; height: 7px; border-radius: 50%; background: rgba(255,255,255,0.14); }
.diff-dot.on.easy { background: #5ec88c; }
.diff-dot.on.moderate { background: #ffd14a; }
.diff-dot.on.hard { background: #ff8c42; }
.diff-dot.on.veryhard { background: #ff5a5a; }
.diff-label { color: var(--muted); font-size: 0.72rem; margin-left: 0.4rem; }

/* --- Streamlit dataframe theming — modern minimal --- */
[data-testid="stDataFrame"] {
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px;
    overflow: hidden;
    background:
        linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 100%),
        rgba(12, 18, 38, 0.55);
    backdrop-filter: blur(14px) saturate(120%);
    -webkit-backdrop-filter: blur(14px) saturate(120%);
    box-shadow: 0 6px 24px rgba(0,0,0,0.25);
}
[data-testid="stDataFrame"] thead th {
    background: transparent !important;
    color: var(--muted) !important;
    font-weight: 600 !important;
    font-size: 0.72rem !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid rgba(255,255,255,0.08) !important;
    padding: 0.85rem 0.9rem !important;
}
[data-testid="stDataFrame"] tbody td {
    background: transparent !important;
    color: var(--text) !important;
    font-size: 0.92rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.03) !important;
    padding: 0.7rem 0.9rem !important;
}
[data-testid="stDataFrame"] tbody tr:hover td {
    background: rgba(74,144,255,0.06) !important;
}
/* Selected-row highlight */
[data-testid="stDataFrame"] tbody tr[aria-selected="true"] td {
    background: rgba(74,144,255,0.12) !important;
}

/* --- Streamlit selectbox / number input — clean dark inputs --- */
[data-baseweb="select"] > div,
[data-testid="stNumberInput"] input,
.stTextInput input {
    background: rgba(12, 18, 38, 0.6) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
    transition: border-color 0.15s;
}
[data-baseweb="select"] > div:hover,
[data-testid="stNumberInput"] input:hover {
    border-color: rgba(74,144,255,0.3) !important;
}

/* --- Headings (h1/h2/h3 wrapped in st.markdown) --- */
h1 { letter-spacing: -0.02em; }
.stMarkdown h2 {
    font-size: 1.1rem; font-weight: 700;
    letter-spacing: 0.1em; text-transform: uppercase;
    color: var(--muted);
    margin: 1.5rem 0 0.5rem;
}

/* =====================================================================
   RESPONSIVE OVERRIDES — keep narrow-viewport behavior in one place so
   we don't have to touch every component block above. Three breakpoints:
     <=1024px : tablet landscape (small tweaks)
     <=768px  : tablet portrait / large phone (collapse 2-cols, shrink nav)
     <=480px  : phone portrait (single column everything, compact tier list)
   ===================================================================== */
@media (max-width: 1024px) {
    .main .block-container { padding-left: 1rem; padding-right: 1rem; }
    .hero h1 { font-size: 2.6rem; }
    .hero p { font-size: 1.05rem; }
    .season-card { padding: 1.4rem 1.5rem; }
    .season-number { font-size: 3rem; }
    .season-title { font-size: 1.25rem; }
    .tier-label { width: 90px; font-size: 2.1rem; }
}

@media (max-width: 768px) {
    /* Layout: shrink container padding so cards don't crush against screen */
    .main .block-container { padding-left: 0.65rem; padding-right: 0.65rem; }

    /* Top nav: wraps and shrinks; search shrinks; brand smaller */
    .wr-nav {
        flex-wrap: wrap; gap: 0.6rem;
        padding: 0.35rem 0.75rem;
        margin: -0.5rem -0.5rem 1rem;
    }
    .brand { height: 62px; }
    .brand img { height: 56px; }
    .wr-nav-links {
        order: 3; width: 100%; justify-content: flex-start;
        gap: 0.1rem; overflow-x: auto; -webkit-overflow-scrolling: touch;
        flex-wrap: nowrap; padding-bottom: 0.15rem;
    }
    .wr-nav-links a {
        font-size: 0.82rem; padding: 0.4rem 0.7rem; flex-shrink: 0;
    }
    .wr-nav .champ-search { width: auto; flex: 1; }
    .wr-nav .champ-search input { font-size: 0.82rem; padding: 0.45rem 0.5rem; }
    .wr-nav .champ-search button { padding: 0 0.85rem; font-size: 0.78rem; }

    /* Hero */
    .hero { padding: 1.75rem 0.5rem 1rem; }
    .hero h1 { font-size: 2rem; }
    .hero p { font-size: 0.98rem; }
    .hero-search-wrap { margin-top: 1.25rem; }
    .hero-search-wrap .champ-search input { padding: 0.75rem 0.95rem; font-size: 0.95rem; }
    .hero-search-wrap .champ-search button { padding: 0 1.2rem; font-size: 0.92rem; }

    /* Cards / grids: padding shrinks */
    .wr-card { padding: 1rem 1.1rem; }
    .season-card { padding: 1.1rem 1.15rem; gap: 1.25rem; }
    .season-emblem { width: 72px; height: 72px; font-size: 2.2rem; }
    .season-number { font-size: 2.4rem; }
    .season-title { font-size: 1.1rem; }
    .season-row { gap: 1rem; }

    /* Featured champion/skin cards on the home season card */
    .season-feature { padding: 0.65rem 0.8rem; gap: 0.65rem; }
    .feature-avatar { width: 44px; height: 44px; }
    .feature-name { font-size: 0.86rem; }

    /* Spotlight (Featured Champion) — splash hero stacks naturally because
       its grid is already `1fr`; just shrink the giant name + stats. */
    .spotlight-card { padding: 1.25rem 1.2rem; min-height: 240px; }
    .spotlight-name { font-size: 2rem !important; }
    .spotlight-stats { grid-template-columns: repeat(2, 1fr); gap: 0.5rem; }
    .sl-stat-value { font-size: 1.25rem !important; }

    /* Stat widget row — already collapses, just shrink internal type */
    .stat-widget { padding: 0.85rem 1rem; }
    .sw-big { font-size: 1.4rem !important; }
    .sw-pct { font-size: 1.4rem !important; }

    /* Tier list: smaller labels + icons so a row can still fit ~6 champs */
    .tier-row { min-height: 92px; gap: 0.5rem; margin-bottom: 0.55rem; }
    .tier-label {
        width: 68px; font-size: 1.7rem; border-radius: 10px;
    }
    .tier-label.tier-god { font-size: 1.1rem; }
    .tier-label.tier-ass { font-size: 1.25rem; }
    .tier-champs { padding: 0.6rem 0.55rem; gap: 0.5rem; border-radius: 10px; }
    .tier-champ { width: 52px; }
    .tier-champ img { width: 44px; height: 44px; }
    .tier-champ .champ-name { font-size: 0.65rem; }
    .tier-champ .champ-wr { font-size: 0.62rem; }
    .tier-champ-icon { width: 44px; height: 44px; }
    .tier-champ-icon img { width: 44px; height: 44px; }

    /* Champion-list cards / meta-rows / role-wr cells */
    .meta-row { grid-template-columns: 64px 1fr 48px !important; gap: 0.5rem; }
    .meta-n { display: none; }

    /* Leaderboard / tables: let any 5-column grid go to 3 */
    .role-wr-grid { grid-template-columns: repeat(2, 1fr) !important; }
}

@media (max-width: 480px) {
    .main .block-container { padding-left: 0.4rem; padding-right: 0.4rem; }

    /* Hero */
    .hero h1 { font-size: 1.65rem; }
    .hero p { font-size: 0.92rem; line-height: 1.45; }
    .hero p .pill { font-size: 0.7rem; padding: 0.05rem 0.4rem; }

    /* Nav: hide nav-link text after brand — just keep search */
    .wr-nav-links a { font-size: 0.78rem; padding: 0.35rem 0.55rem; }
    .brand img { height: 46px; }
    .brand { height: 52px; }

    /* Spotlight: stack everything vertically */
    .spotlight-card { padding: 1rem 0.9rem; min-height: auto; }
    .spotlight-name { font-size: 1.7rem !important; }
    .spotlight-stats { grid-template-columns: 1fr 1fr; gap: 0.4rem; }
    .sl-stat-label { font-size: 0.6rem !important; }
    .sl-stat-value { font-size: 1.1rem !important; }

    /* Tier list: drop ranks even more for 5-champ rows */
    .tier-row { min-height: 80px; gap: 0.4rem; }
    .tier-label { width: 52px; font-size: 1.4rem; }
    .tier-label.tier-god { font-size: 0.88rem; letter-spacing: 0; }
    .tier-label.tier-ass { font-size: 0.95rem; }
    .tier-champ { width: 44px; }
    .tier-champ img { width: 38px; height: 38px; }
    .tier-champ-icon { width: 38px; height: 38px; }
    .tier-champ-icon img { width: 38px; height: 38px; }
    .tier-champ .champ-name { font-size: 0.6rem; }
    .tier-champ .champ-wr { display: none; }

    /* Cards */
    .wr-card { padding: 0.85rem 0.9rem; border-radius: 11px; }
    .season-card { padding: 0.95rem 0.95rem; }
    .season-emblem { width: 60px; height: 60px; font-size: 1.8rem; }
    .season-number { font-size: 2rem; }
    .season-row { gap: 0.8rem; }

    /* Stat widgets */
    .sw-big { font-size: 1.2rem !important; }
    .sw-pct { font-size: 1.2rem !important; }
    .sw-eyebrow { font-size: 0.6rem !important; }

    /* Tables/lists — generic 4+ column grids collapse */
    .meta-row {
        grid-template-columns: 52px 1fr 44px !important;
        padding: 0.35rem 0.5rem !important;
    }
    /* Stub / coming-soon cards */
    .stub-card { padding: 0.9rem 1rem; font-size: 0.85rem; }
}

/* Ensure images never overflow on any device */
img { max-width: 100%; height: auto; }

/* Streamlit's dataframe gets a horizontal scroll instead of bursting layout */
[data-testid="stDataFrame"] { overflow-x: auto; }
</style>
"""


def inject_css() -> None:
    """Drop the WRTrueMeta theme into the current page."""
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def top_nav(active: str = "Home", champions: list[str] | None = None) -> None:
    """Render the visual top nav (custom HTML).

    The search box is a real HTML form that submits to the Leaderboard
    page with `?champion=<name>`. The Leaderboard page reads that param
    and pre-selects the champion. Datalist provides typeahead suggestions
    populated from `champions`.

    `active` is only used to highlight which link to mark current.
    """
    # Import here to avoid a circular import at module load time.
    from web.local_assets import logo

    items = [
        ("Home", "/"),
        ("Champions", "Champions"),
        ("Leaderboard", "Leaderboard"),
        ("Tier List", "Tier_List"),
        ("Methodology", "Methodology"),
    ]
    links_html = "".join(
        f'<a href="{href}" target="_self" class="{ "active" if name == active else "" }">{name}</a>'
        for name, href in items
    )
    options_html = "".join(f'<option value="{c}">' for c in (champions or []))
    search_icon = (
        '<svg class="search-icon" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"><circle cx="11" cy="11" r="7"></circle>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>'
    )
    st.markdown(
        f"""
        <div class="wr-nav">
          <a class="brand" href="/" target="_self"><img src="{logo()}" alt="WrTrueMeta.com" /></a>
          <div class="wr-nav-links">{links_html}</div>
          <form class="champ-search" action="/Leaderboard" method="get" autocomplete="off">
            {search_icon}
            <input name="champion" type="text" list="nav-champ-datalist"
                   placeholder="Search champion..." autocomplete="off" />
            <datalist id="nav-champ-datalist">{options_html}</datalist>
            <button type="submit">Find</button>
          </form>
        </div>
        """,
        unsafe_allow_html=True,
    )
