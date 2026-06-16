"""Generate fully static, SEO-optimised HTML pages for Google to crawl.

The Streamlit app is JS-rendered, so Google can't reliably index its content.
This script reads the same data the live app uses and emits a set of static
HTML files that contain all content as real text in the initial HTTP response
— exactly what Google's crawler wants.

Pages emitted:
  * landing/tier-list.html           — full tier list (already shipping)
  * landing/champions.html           — champion directory / index
  * landing/champions/<slug>.html    — one per scraped champion, with stats,
                                       best player, and a builds-coming-soon
                                       section targeting "<champion> build"
                                       search traffic
  * landing/builds.html              — main builds landing page (stub for
                                       launch, ranks for "Wild Rift builds")

Each page has its own JSON-LD structured data, OG tags, canonical URL, and
keyword-targeted title/description. Sitemap is updated automatically.

Run after every data refresh:

    python -m scripts.build_seo_tier_list

Or wire it into the scrape pipeline so the pages regenerate automatically.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from html import escape
from pathlib import Path

import pandas as pd

# Make sibling packages importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.champion_assets import icon_url, splash_url, to_ddragon_key
from web.champion_meta import champion_class, champion_difficulty, difficulty_label
from web.champion_roles import roles_for
from web.data_loader import (
    assign_tier,
    champion_summary,
    load_leaderboard,
    tier_order,
)


OUT_PATH = ROOT / "landing" / "tier-list.html"
CANONICAL = "https://wrtruemeta.com/tier-list"


def _build_buckets(summary: pd.DataFrame):
    buckets: dict[str, list[dict]] = {label: [] for label, _ in tier_order()}
    for _, row in summary.sort_values("weighted_winrate", ascending=False).iterrows():
        wr = row["weighted_winrate"]
        if pd.isna(wr):
            continue
        label, css = assign_tier(float(wr))
        diff_word = difficulty_label(int(row["difficulty"]))
        buckets[label].append({
            "champion": str(row["champion"]),
            "wr": float(wr),
            "ceiling": float(row["max_winrate"]) if pd.notna(row["max_winrate"]) else None,
            "median_games": int(row["median_games"]) if pd.notna(row["median_games"]) else None,
            "class": row["champ_class"],
            "role": roles_for(str(row["champion"]))[0],
            "difficulty": diff_word,
            "is_hard": diff_word in ("Hard", "Very Hard"),
            "is_otp": bool(row.get("is_otp", False)),
            "css_tier": css,
        })
    return buckets


def _render_champion_li(c: dict) -> str:
    name = escape(c["champion"])
    icon = icon_url(c["champion"])
    badges = []
    if c["is_otp"]:
        badges.append('<span class="badge badge-otp" title="One-trick pony">OTP</span>')
    if c["is_hard"]:
        badges.append('<span class="badge badge-hard" title="Hard mechanics">Hard</span>')
    badges_html = "".join(badges)
    title_attr = f'{name} — {c["wr"]:.1f}% top-50 win rate'
    if c["ceiling"] is not None:
        title_attr += f', ceiling {c["ceiling"]:.1f}%'
    return (
        f'<li class="champ" title="{title_attr}">'
        f'<a href="https://wrtruemeta.streamlit.app/Leaderboard?champion={escape(c["champion"])}" '
        f'rel="bookmark">'
        f'<div class="champ-icon{" diff-hard" if c["is_hard"] else ""}">'
        f'<img src="{icon}" alt="{name} Wild Rift icon" loading="lazy" width="56" height="56" />'
        f'{badges_html}'
        f'</div>'
        f'<span class="champ-name">{name}</span>'
        f'<span class="champ-wr">{c["wr"]:.1f}%</span>'
        f'</a></li>'
    )


def _render_tier_row(label: str, css_class: str, champs: list[dict]) -> str:
    if not champs:
        body = '<p class="tier-empty">No champions in this tier.</p>'
    else:
        body = '<ul class="tier-champs">' + "".join(_render_champion_li(c) for c in champs) + "</ul>"
    return (
        f'<section class="tier-row" aria-label="{label} tier">'
        f'  <div class="tier-label tier-{css_class}"><span>{label}</span></div>'
        f'  <div class="tier-strip">'
        f'    <h2 class="tier-h">{label} tier <span class="tier-count">&middot; {len(champs)} champion{"s" if len(champs) != 1 else ""}</span></h2>'
        f'    {body}'
        f'  </div>'
        f'</section>'
    )


def _json_ld(summary: pd.DataFrame, updated: str) -> str:
    """ItemList structured data — helps Google render the tier list as a list."""
    items = []
    for i, (_, r) in enumerate(
        summary.sort_values("weighted_winrate", ascending=False).iterrows(), start=1
    ):
        if pd.isna(r["weighted_winrate"]):
            continue
        items.append({
            "@type": "ListItem",
            "position": i,
            "name": str(r["champion"]),
            "url": f"https://wrtruemeta.streamlit.app/Leaderboard?champion={r['champion']}",
        })
        if i >= 50:
            break  # Google rarely cares past the top 50

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": f"{CANONICAL}#webpage",
                "url": CANONICAL,
                "name": "Wild Rift Tier List — EU Top 50 Player Win Rates",
                "datePublished": updated,
                "dateModified": updated,
                "inLanguage": "en",
                "isPartOf": {"@id": "https://wrtruemeta.com/#website"},
            },
            {
                "@type": "ItemList",
                "name": "Wild Rift Champion Tier List (EU)",
                "description": "Wild Rift champions ranked by the games-weighted, confidence-adjusted win rate of their top 50 EU players.",
                "url": CANONICAL,
                "numberOfItems": len(items),
                "itemListElement": items,
            },
        ],
    }
    import json
    return f'<script type="application/ld+json">{json.dumps(schema)}</script>'


def build() -> str:
    df = load_leaderboard()
    if df.empty:
        raise SystemExit("data/winrates.csv is empty — scrape some champions first.")
    summary = champion_summary(df)
    buckets = _build_buckets(summary)
    updated = date.today().isoformat()
    # Windows strftime doesn't support `%-d`, so stitch the day in by hand.
    today = date.today()
    rendered = f"{today.strftime('%B')} {today.day}, {today.year}"

    n_tracked = len(summary)
    top_champ = summary.iloc[0]["champion"]
    top_wr = summary.iloc[0]["weighted_winrate"]
    bottom_champ = summary.iloc[-1]["champion"]
    bottom_wr = summary.iloc[-1]["weighted_winrate"]

    tier_html = "\n".join(
        _render_tier_row(label, css_class, buckets[label])
        for label, css_class in tier_order()
    )

    ld = _json_ld(summary, updated)

    return TEMPLATE.format(
        canonical=CANONICAL,
        updated=updated,
        rendered=rendered,
        n_tracked=n_tracked,
        top_champ=escape(top_champ),
        top_wr=f"{top_wr:.1f}",
        bottom_champ=escape(bottom_champ),
        bottom_wr=f"{bottom_wr:.1f}",
        tiers=tier_html,
        json_ld=ld,
    )


# ---------- HTML template -----------------------------------------------

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">

<title>Wildrift Tier List ({rendered}) — League of Legends Wildrift EU Top 50 | WrTrueMeta</title>
<meta name="description" content="The League of Legends Wildrift tier list ranked by real top-50 EU player win rates. {n_tracked} champions across GOD, S, A, B, C and Ass tiers — updated twice a month. Highest WR: {top_champ} ({top_wr}%).">
<meta name="keywords" content="Wildrift tier list, Wild Rift tier list, League of Legends Wildrift tier list, LoL Wildrift tier list, Wildrift meta, Wild Rift meta, Wildrift win rates, Wildrift champion stats, best Wildrift champions, WR tier list, Wildrift EU tier list, Wild Rift EU tier list, Wildrift S21">
<meta name="author" content="WrTrueMeta">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">

<!-- Open Graph -->
<meta property="og:site_name" content="WrTrueMeta">
<meta property="og:title" content="Wild Rift Tier List ({rendered}) — Top 50 EU Win Rates">
<meta property="og:description" content="The Wild Rift tier list ranked by real top-50 EU player win rates. {n_tracked} champions tracked, updated twice a month.">
<meta property="og:image" content="https://wrtruemeta.com/landing_bg.jpg">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="article">

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Wild Rift Tier List ({rendered})">
<meta name="twitter:description" content="Wild Rift champions ranked by real top-50 EU player win rates.">
<meta name="twitter:image" content="https://wrtruemeta.com/landing_bg.jpg">

<meta name="theme-color" content="#070b18">
<link rel="icon" type="image/png" href="logo.png?v=2">
<link rel="apple-touch-icon" href="logo.png?v=2">

{json_ld}

<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #070b18; --bg-2: #0c1226; --card: #121a30; --card-2: #1a2240;
    --border: rgba(255,255,255,0.07); --border-2: rgba(255,255,255,0.04);
    --text: #e6ecff; --muted: #8a92a8;
    --accent: #4a90ff; --gold: #ffd76e; --bad: #ff5a5a;
  }}
  html {{ scroll-behavior: smooth; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 Oxygen, Ubuntu, Cantarell, sans-serif;
    color: var(--text);
    background:
      radial-gradient(circle at 20% -10%, rgba(74,144,255,0.08), transparent 50%),
      radial-gradient(circle at 80% 110%, rgba(74,144,255,0.05), transparent 50%),
      var(--bg);
    min-height: 100vh;
    padding: 2rem 1rem 4rem;
    line-height: 1.55;
  }}
  .container {{ max-width: 1180px; margin: 0 auto; }}
  header.brand {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 2rem;
  }}
  header.brand a {{ color: inherit; text-decoration: none; display: inline-flex; align-items: center; gap: 0.6rem; font-size: 1.05rem; font-weight: 700; }}
  header.brand img {{ height: 52px; width: auto; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }}
  header.brand nav a {{ color: var(--muted); margin-left: 1.3rem; text-decoration: none; font-size: 0.92rem; font-weight: 600; }}
  header.brand nav a:hover {{ color: var(--accent); }}

  h1 {{
    font-size: clamp(1.8rem, 4.2vw, 2.9rem);
    font-weight: 800; letter-spacing: -0.02em; line-height: 1.1;
    margin-bottom: 0.8rem;
  }}
  h1 .accent {{ color: var(--accent); }}
  .lead {{
    color: rgba(230,236,255,0.85);
    font-size: 1.1rem; max-width: 760px;
    margin-bottom: 1.5rem;
  }}
  .lead .pill {{
    display: inline-block;
    background: rgba(74,144,255,0.18);
    color: var(--accent);
    border: 1px solid rgba(74,144,255,0.35);
    padding: 0.1rem 0.55rem;
    border-radius: 999px;
    font-size: 0.85em; font-weight: 700;
  }}
  .meta-line {{ color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }}
  .summary-stats {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 0.7rem;
    margin: 1.5rem 0 2rem;
  }}
  .stat-card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 0.9rem 1.1rem;
  }}
  .stat-card-label {{ color: var(--muted); font-size: 0.65rem; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700; }}
  .stat-card-value {{ font-size: 1.4rem; font-weight: 800; margin-top: 0.35rem; color: var(--text); }}
  .stat-card-value.accent {{ color: var(--accent); }}
  .stat-card-value.bad {{ color: var(--bad); }}

  /* Tier rows */
  .tier-row {{
    display: flex; gap: 0.85rem; min-height: 110px;
    margin-bottom: 0.9rem; align-items: stretch;
  }}
  @media (max-width: 720px) {{
    .tier-row {{ flex-direction: column; }}
  }}
  .tier-label {{
    flex-shrink: 0; width: 104px;
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 2rem; font-weight: 900; letter-spacing: -0.04em;
    color: #fff;
    box-shadow: 0 4px 14px rgba(0,0,0,0.3);
  }}
  @media (max-width: 720px) {{
    .tier-label {{ width: 100%; min-height: 60px; }}
  }}
  .tier-label.tier-tier-god {{ background: linear-gradient(135deg, #ffd24a, #e53916); }}
  .tier-label.tier-tier-s   {{ background: linear-gradient(135deg, #ff8c42, #ff6b1a); }}
  .tier-label.tier-tier-a   {{ background: linear-gradient(135deg, #ffd14a, #f5b800); color: #2a1500; }}
  .tier-label.tier-tier-b   {{ background: linear-gradient(135deg, #4a90ff, #2b6ad6); }}
  .tier-label.tier-tier-c   {{ background: linear-gradient(135deg, #8a92a8, #5a6378); }}
  .tier-label.tier-tier-ass {{ background: linear-gradient(135deg, #4a5066, #2a2e3e); color: #aeb4c6; }}

  .tier-strip {{
    flex: 1;
    background: rgba(12,18,38,0.55);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 0.85rem 1rem;
  }}
  .tier-h {{
    color: var(--muted);
    font-size: 0.72rem; font-weight: 700;
    letter-spacing: 0.14em; text-transform: uppercase;
    margin-bottom: 0.65rem;
  }}
  .tier-h .tier-count {{ color: var(--muted); font-weight: 500; }}

  .tier-champs {{
    list-style: none; display: flex; flex-wrap: wrap; gap: 0.7rem;
  }}
  .champ {{
    width: 64px; text-align: center;
  }}
  .champ a {{
    color: inherit; text-decoration: none;
    display: flex; flex-direction: column; align-items: center;
  }}
  .champ-icon {{
    position: relative; width: 56px; height: 56px;
  }}
  .champ-icon img {{
    width: 56px; height: 56px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,0.06);
    object-fit: cover; display: block;
    transition: transform 0.18s, border-color 0.18s, box-shadow 0.18s;
  }}
  .champ-icon.diff-hard img {{
    border-color: var(--bad);
    box-shadow: 0 0 6px rgba(255,90,90,0.45);
  }}
  .champ a:hover .champ-icon img {{
    transform: translateY(-2px);
    border-color: rgba(74,144,255,0.4);
  }}
  .champ-name {{
    color: var(--text); font-size: 0.72rem; font-weight: 500;
    margin-top: 0.3rem;
    max-width: 64px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .champ-wr {{
    color: var(--accent); font-size: 0.7rem; font-weight: 700;
  }}

  .badge {{
    position: absolute; top: -4px;
    font-size: 0.55rem; font-weight: 800; letter-spacing: 0.04em;
    color: #fff; border-radius: 4px;
    padding: 1px 4px; border: 1px solid rgba(0,0,0,0.45);
  }}
  .badge-otp {{
    right: -6px;
    background: linear-gradient(135deg, #ff8c42, #e2531a);
    box-shadow: 0 0 8px rgba(255,140,66,0.55);
  }}
  .badge-hard {{
    left: -6px;
    background: linear-gradient(135deg, #ff7575, #d23030);
    box-shadow: 0 0 6px rgba(255,90,90,0.5);
  }}
  .tier-empty {{ color: var(--muted); font-style: italic; padding: 0.5rem; }}

  /* Legend */
  .legend {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 12px; padding: 1rem 1.25rem; margin: 2rem 0;
    color: rgba(230,236,255,0.85); font-size: 0.92rem;
  }}
  .legend h3 {{ font-size: 0.8rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.6rem; }}
  .legend p {{ margin: 0.4rem 0; }}

  /* CTA */
  .cta {{
    background: linear-gradient(135deg, rgba(74,144,255,0.15), rgba(74,144,255,0.04));
    border: 1px solid rgba(74,144,255,0.3);
    border-radius: 14px;
    padding: 1.5rem 1.75rem;
    text-align: center;
    margin: 2.5rem 0;
  }}
  .cta a {{
    display: inline-block;
    margin-top: 0.8rem;
    padding: 0.7rem 1.5rem;
    background: var(--accent); color: #fff;
    border-radius: 10px; text-decoration: none;
    font-weight: 700;
  }}
  .cta a:hover {{ background: #5fa0ff; }}

  footer.site {{
    color: var(--muted); font-size: 0.78rem;
    text-align: center; padding-top: 2rem; line-height: 1.7;
  }}
  footer.site a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<div class="container">
  <header class="brand">
    <a href="/" rel="home">
      <img src="logo.png?v=2" alt="WrTrueMeta logo" />
    </a>
    <nav>
      <a href="/">Home</a>
      <a href="https://wrtruemeta.streamlit.app/Tier_List">Live tier list</a>
    </nav>
  </header>

  <h1>Wild Rift <span class="accent">Tier List</span></h1>
  <p class="lead">
    Real <span class="pill">EU</span> Wild Rift champion rankings from the
    <span class="pill">top 50</span> players of every champion &mdash; built
    from in-game leaderboards, not guessed from public match samples. Updated
    <span class="pill">twice a month</span>.
  </p>
  <p class="meta-line">Last updated: <strong>{rendered}</strong> &middot; {n_tracked} champions tracked &middot; sorted by confidence-adjusted win rate.</p>

  <section class="summary-stats" aria-label="Top-level summary">
    <div class="stat-card">
      <div class="stat-card-label">Top Pick</div>
      <div class="stat-card-value accent">{top_champ}</div>
      <div class="stat-card-label" style="margin-top:0.3rem;">{top_wr}% win rate</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Weakest Pick</div>
      <div class="stat-card-value bad">{bottom_champ}</div>
      <div class="stat-card-label" style="margin-top:0.3rem;">{bottom_wr}% win rate</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Champions Tracked</div>
      <div class="stat-card-value">{n_tracked}</div>
      <div class="stat-card-label" style="margin-top:0.3rem;">EU top-50 each</div>
    </div>
    <div class="stat-card">
      <div class="stat-card-label">Refresh Cadence</div>
      <div class="stat-card-value">Bi-monthly</div>
      <div class="stat-card-label" style="margin-top:0.3rem;">Twice a month</div>
    </div>
  </section>

  <article aria-label="Wild Rift tier list">
    {tiers}
  </article>

  <section class="legend" aria-label="How to read this tier list">
    <h3>How to read the tier list</h3>
    <p><strong>The win rates are all above 50% on purpose.</strong> These are elite EU mains, and elite mains win more than average. A low number means the champion is weaker at high level, not a losing pick. If you&rsquo;re a top-tier player and you&rsquo;re below a champion&rsquo;s listed win rate, you&rsquo;re underperforming on that champion.</p>
    <p><strong>Gap reading:</strong> each percentage point is roughly one extra win per 100 games. A 2-point gap = one tier; 4+ points = clearly stronger at high level.</p>
    <p><strong>Red border</strong> on an icon means Hard or Very Hard mechanical difficulty &mdash; not for beginners. <strong>OTP badge</strong> means the player base is heavily skewed toward one-tricks (a few dedicated grinders dominate the stats).</p>
  </section>

  <section class="cta">
    <h2 style="font-size:1.4rem; margin-bottom:0.4rem;">Want the live interactive tier list?</h2>
    <p style="color:rgba(230,236,255,0.85);">Filter by role, save as a PNG, see per-champion leaderboards.</p>
    <a href="https://wrtruemeta.streamlit.app/Tier_List">Open the live tier list &rarr;</a>
  </section>

  <footer class="site">
    Questions or feedback? DM <strong style="color:var(--accent);">@generalthr4gg</strong> on Discord.<br/>
    Not affiliated with Riot Games. League of Legends &amp; Wild Rift are &copy; Riot Games, Inc.<br/>
    Champion artwork via <a href="https://developer.riotgames.com/docs/lol#data-dragon" target="_blank" rel="noopener">DDragon</a>.
    Methodology: top-50 confidence-adjusted win rate, twice-monthly refresh.
  </footer>
</div>
</body>
</html>
"""


def champion_to_slug(name: str) -> str:
    """URL slug for per-champion pages. Lowercase + hyphenated."""
    import re
    s = name.lower().replace("&", "and").replace("'", "")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


# ---------- Per-champion page -------------------------------------------

def build_champion_page(c: dict, df, summary) -> str:
    """Render a single champion's SEO page.

    `c` is a row dict from champion_summary. Page contains:
      * Champion-specific title/description/keywords for search targeting
      * Stats grid (tier, WR, ceiling, median games, class, difficulty, role)
      * Best player section
      * Builds coming-soon section — full keyword presence for "<champ> build"
      * Related champions in the same role
    """
    from web.data_loader import best_player_per_champion

    name = c["champion"]
    slug = champion_to_slug(name)
    role = roles_for(name)[0]
    cls = champion_class(name)
    diff_word = difficulty_label(int(c["difficulty"]))
    tier_label, tier_css = assign_tier(c["weighted_winrate"])
    wr = float(c["weighted_winrate"])
    ceiling = float(c["max_winrate"]) if pd.notna(c["max_winrate"]) else None
    median_g = int(c["median_games"]) if pd.notna(c["median_games"]) else None
    is_otp = bool(c.get("is_otp", False))
    is_hard = diff_word in ("Hard", "Very Hard")

    # Best player (Wilson) on this champion
    best_df = best_player_per_champion(df[df["champion"] == name])
    best_flag = best_df[best_df["is_best_for_champ"]]
    if not best_flag.empty:
        b = best_flag.iloc[0]
        best_player = str(b["player_name"])
        best_rank = int(b["rank"]) if pd.notna(b["rank"]) else None
        best_conf = float(b["confidence_wr"])
        best_section = (
            f'<p>The best <strong>{escape(name)}</strong> player tracked on EU '
            f'is <strong>{escape(best_player)}</strong>'
            f'{f" (rank #{best_rank})" if best_rank else ""}, '
            f'with a confidence-adjusted win rate of <strong>{best_conf:.1f}%</strong>. '
            f'This score uses the Wilson lower bound, so it favours demonstrated '
            f'high-volume performance over a few lucky games.</p>'
        )
    else:
        best_section = '<p>Best-player data is being collected.</p>'

    related = []
    for _, r in summary.iterrows():
        if r["champion"] == name:
            continue
        if roles_for(r["champion"])[0] == role:
            related.append(r)
        if len(related) >= 6:
            break
    related_html = "".join(
        f'<a class="related-champ" href="/champions/{champion_to_slug(r["champion"])}">'
        f'<img src="{icon_url(r["champion"])}" alt="{escape(r["champion"])} Wild Rift icon" '
        f'loading="lazy" width="44" height="44" />'
        f'<span>{escape(r["champion"])}</span>'
        f'<small>{float(r["weighted_winrate"]):.1f}%</small>'
        f'</a>'
        for r in related
    )

    badges = []
    if is_otp:
        badges.append('<span class="champ-badge badge-otp">OTP</span>')
    if is_hard:
        badges.append('<span class="champ-badge badge-hard">Hard</span>')
    badges_html = "".join(badges)

    today = date.today()
    updated = today.isoformat()
    rendered = f"{today.strftime('%B')} {today.day}, {today.year}"

    title = f"{name} Wildrift Win Rate, Tier & Build ({rendered}) | WrTrueMeta"
    desc = (
        f"{name} is currently {tier_label} tier in League of Legends Wildrift "
        f"with a {wr:.1f}% top-50 EU win rate. See {name}'s Wild Rift stats, "
        f"best player, and build (coming soon). Updated twice a month."
    )
    keywords = (
        f"{name} Wildrift, {name} Wild Rift, {name} build, {name} Wildrift build, "
        f"{name} runes, {name} items, {name} win rate, {name} tier, {name} guide, "
        f"Wildrift {name}, Wild Rift {name}, League of Legends Wildrift {name}, "
        f"LoL Wildrift {name}, best {name} build, {name} {role.lower()}"
    )
    canonical = f"https://wrtruemeta.com/champions/{slug}"

    json_ld = (
        '<script type="application/ld+json">'
        f'{{"@context":"https://schema.org","@type":"WebPage",'
        f'"@id":"{canonical}#webpage",'
        f'"url":"{canonical}",'
        f'"name":{json.dumps(title)},'
        f'"datePublished":"{updated}","dateModified":"{updated}",'
        f'"inLanguage":"en",'
        f'"isPartOf":{{"@id":"https://wrtruemeta.com/#website"}},'
        f'"breadcrumb":{{"@type":"BreadcrumbList","itemListElement":['
        f'{{"@type":"ListItem","position":1,"name":"Home","item":"https://wrtruemeta.com/"}},'
        f'{{"@type":"ListItem","position":2,"name":"Champions","item":"https://wrtruemeta.com/champions"}},'
        f'{{"@type":"ListItem","position":3,"name":"{name}","item":"{canonical}"}}'
        f']}}}}'
        '</script>'
    )

    return _render(CHAMP_TEMPLATE, {
        "canonical": canonical,
        "title": escape(title),
        "desc": escape(desc),
        "keywords": escape(keywords),
        "json_ld": json_ld,
        "rendered": rendered,
        "name": escape(name),
        "slug": slug,
        "icon_url": icon_url(name),
        "splash_url": splash_url(name),
        "role": escape(role),
        "cls": escape(cls),
        "diff_word": escape(diff_word),
        "tier_label": tier_label,
        "tier_css": tier_css,
        "wr": f"{wr:.1f}",
        "ceiling": f"{ceiling:.1f}" if ceiling is not None else "—",
        "median_g": f"{median_g:,}" if median_g else "—",
        "badges": badges_html,
        "best_section": best_section,
        "related_html": related_html,
    })


def _render(tpl: str, ctx: dict) -> str:
    """Placeholder substitution without parsing CSS braces. {key} → ctx[key]."""
    out = tpl
    for k, v in ctx.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# ---------- Champion index ----------------------------------------------

def build_champion_index(summary) -> str:
    cards = []
    for _, r in summary.iterrows():
        name = str(r["champion"])
        slug = champion_to_slug(name)
        wr = float(r["weighted_winrate"]) if pd.notna(r["weighted_winrate"]) else None
        tier_label, tier_css = assign_tier(wr) if wr is not None else ("?", "tier-unknown")
        wr_text = f'<span class="ci-wr">{wr:.1f}%</span>' if wr is not None else ""
        cards.append(
            f'<a class="ci-card" href="/champions/{slug}">'
            f'<img src="{icon_url(name)}" alt="{escape(name)} Wild Rift icon" '
            f'loading="lazy" width="56" height="56" />'
            f'<div class="ci-meta">'
            f'<span class="ci-name">{escape(name)}</span>'
            f'<span class="ci-tier tier-{tier_css}">{tier_label}</span>'
            f'</div>'
            f'{wr_text}'
            f'</a>'
        )

    today = date.today()
    rendered = f"{today.strftime('%B')} {today.day}, {today.year}"
    return _render(INDEX_TEMPLATE, {
        "canonical": "https://wrtruemeta.com/champions",
        "rendered": rendered,
        "n": len(summary),
        "cards": "".join(cards),
    })


# ---------- Builds landing page -----------------------------------------

def build_builds_page(summary) -> str:
    """SEO landing page targeting 'Wild Rift builds' searches."""
    # Show top 12 champs as a teaser of "coming-soon builds".
    teasers = []
    for _, r in summary.head(12).iterrows():
        name = str(r["champion"])
        teasers.append(
            f'<a class="b-tile" href="/champions/{champion_to_slug(name)}">'
            f'<img src="{icon_url(name)}" alt="{escape(name)} Wild Rift build icon" '
            f'loading="lazy" width="56" height="56" />'
            f'<span>{escape(name)}</span>'
            f'</a>'
        )
    today = date.today()
    rendered = f"{today.strftime('%B')} {today.day}, {today.year}"
    return _render(BUILDS_TEMPLATE, {
        "canonical": "https://wrtruemeta.com/builds",
        "rendered": rendered,
        "teasers": "".join(teasers),
    })


# ---------- Templates --------------------------------------------------

_SHARED_HEAD_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #070b18; --card: #121a30; --card-2: #1a2240;
  --border: rgba(255,255,255,0.07); --text: #e6ecff; --muted: #8a92a8;
  --accent: #4a90ff; --gold: #ffd76e; --bad: #ff5a5a;
}
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--text);
  background:
    radial-gradient(circle at 20% -10%, rgba(74,144,255,0.08), transparent 50%),
    radial-gradient(circle at 80% 110%, rgba(74,144,255,0.05), transparent 50%),
    var(--bg);
  min-height: 100vh; padding: 2rem 1rem 4rem; line-height: 1.55;
}
.container { max-width: 1180px; margin: 0 auto; }
header.brand { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; }
header.brand a { color: inherit; text-decoration: none; }
header.brand img { height: 52px; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }
header.brand nav a { color: var(--muted); margin-left: 1.3rem; text-decoration: none; font-size: 0.92rem; font-weight: 600; }
header.brand nav a:hover { color: var(--accent); }
h1 { font-size: clamp(1.8rem, 4.2vw, 2.9rem); font-weight: 800; letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 0.8rem; }
h1 .accent { color: var(--accent); }
.lead { color: rgba(230,236,255,0.85); font-size: 1.1rem; max-width: 760px; margin-bottom: 1.5rem; }
.lead .pill { display: inline-block; background: rgba(74,144,255,0.18); color: var(--accent); border: 1px solid rgba(74,144,255,0.35); padding: 0.1rem 0.55rem; border-radius: 999px; font-size: 0.85em; font-weight: 700; }
footer.site { color: var(--muted); font-size: 0.78rem; text-align: center; padding-top: 2rem; line-height: 1.7; }
footer.site a { color: var(--accent); text-decoration: none; }
"""

CHAMP_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="keywords" content="{keywords}">
<meta name="author" content="WrTrueMeta">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:site_name" content="WrTrueMeta">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:image" content="{splash_url}">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="article">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<meta name="twitter:image" content="{splash_url}">
<meta name="theme-color" content="#070b18">
<link rel="icon" type="image/png" href="/logo.png?v=2">
{json_ld}
<style>""" + _SHARED_HEAD_CSS + """
.champ-hero { position: relative; border-radius: 16px; overflow: hidden; min-height: 260px;
  border: 1px solid var(--border); box-shadow: 0 10px 32px rgba(0,0,0,0.4); margin-bottom: 1.5rem; }
.champ-hero-bg { position: absolute; inset: 0; background-image: url("{splash_url}");
  background-size: cover; background-position: 70% 25%; z-index: 0; }
.champ-hero-overlay { position: absolute; inset: 0; z-index: 1;
  background: linear-gradient(95deg, rgba(7,11,24,0.95), rgba(7,11,24,0.45) 60%, rgba(7,11,24,0.05)); }
.champ-hero-content { position: relative; z-index: 2; padding: 1.6rem 1.8rem; }
.champ-eyebrow { color: var(--accent); font-size: 0.72rem; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; margin-bottom: 0.6rem; }
.champ-title-row { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 0.6rem; }
.champ-title-row img { width: 64px; height: 64px; border-radius: 50%; border: 2px solid rgba(255,255,255,0.15); }
.champ-name-big { font-size: 2.4rem; font-weight: 800; letter-spacing: -0.02em; }
.champ-tags { color: rgba(230,236,255,0.88); font-size: 0.95rem; font-weight: 600; }
.champ-tags .sep { color: var(--muted); }
.champ-badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 6px; font-weight: 800; font-size: 0.7rem; color: #fff; margin-left: 0.4rem; }
.champ-badge.badge-otp { background: linear-gradient(135deg, #ff8c42, #e2531a); }
.champ-badge.badge-hard { background: linear-gradient(135deg, #ff7575, #d23030); }

.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap: 0.7rem; max-width: 720px; }
.stat { background: rgba(7,11,24,0.55); border: 1px solid var(--border); border-radius: 12px; padding: 0.75rem 0.95rem; backdrop-filter: blur(10px); }
.stat-l { color: var(--muted); font-size: 0.62rem; letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700; margin-bottom: 0.3rem; }
.stat-v { font-size: 1.4rem; font-weight: 800; }
.stat-v.accent { color: var(--accent); }
.stat-v.gold { color: var(--gold); }
.stat-v.tier-god { color: #ff7a3c; } .stat-v.tier-s { color: #ff8c42; } .stat-v.tier-a { color: #ffd14a; }
.stat-v.tier-b { color: #4a90ff; } .stat-v.tier-c { color: #8a92a8; } .stat-v.tier-ass { color: #6a7088; }

section.block { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 1.25rem 1.5rem; margin: 1.5rem 0; }
section.block h2 { font-size: 1.3rem; font-weight: 800; margin-bottom: 0.7rem; }
section.block p { color: rgba(230,236,255,0.88); margin-bottom: 0.7rem; }
section.block.builds { background: linear-gradient(135deg, rgba(212,166,74,0.12), rgba(74,144,255,0.05)); border-color: rgba(212,166,74,0.3); }
.builds-coming { display: inline-block; color: var(--gold); font-weight: 700; padding: 0.3rem 0.8rem; border: 1px solid rgba(212,166,74,0.45); border-radius: 999px; font-size: 0.85rem; background: rgba(212,166,74,0.12); margin-bottom: 0.7rem; }

.related-grid { display: flex; flex-wrap: wrap; gap: 0.5rem; }
.related-champ { display: flex; flex-direction: column; align-items: center; width: 80px; padding: 0.55rem; border: 1px solid var(--border); border-radius: 10px; text-decoration: none; color: var(--text); transition: border-color 0.15s, transform 0.15s; }
.related-champ:hover { border-color: rgba(74,144,255,0.4); transform: translateY(-2px); }
.related-champ img { border-radius: 50%; border: 1px solid rgba(255,255,255,0.1); }
.related-champ span { font-size: 0.78rem; margin-top: 0.3rem; }
.related-champ small { color: var(--accent); font-size: 0.7rem; font-weight: 700; }

.cta { background: linear-gradient(135deg, rgba(74,144,255,0.15), rgba(74,144,255,0.04)); border: 1px solid rgba(74,144,255,0.3); border-radius: 14px; padding: 1.25rem 1.5rem; text-align: center; margin: 2rem 0; }
.cta a { display: inline-block; margin-top: 0.6rem; padding: 0.6rem 1.4rem; background: var(--accent); color: #fff; border-radius: 10px; text-decoration: none; font-weight: 700; }
</style>
</head>
<body>
<div class="container">
  <header class="brand">
    <a href="/" rel="home"><img src="/logo.png?v=2" alt="WrTrueMeta logo" /></a>
    <nav>
      <a href="/">Home</a>
      <a href="https://wrtruemeta.streamlit.app/Tier_List">Tier List</a>
      <a href="https://wrtruemeta.streamlit.app/Champions">Champions</a>
      <a href="https://wrtruemeta.streamlit.app/Leaderboard">Leaderboards</a>
      <a class="open-app" href="https://wrtruemeta.streamlit.app" style="color:var(--accent);">Open App &rarr;</a>
    </nav>
  </header>

  <article>
    <div class="champ-hero">
      <div class="champ-hero-bg" role="presentation"></div>
      <div class="champ-hero-overlay" role="presentation"></div>
      <div class="champ-hero-content">
        <div class="champ-eyebrow">Wild Rift &middot; EU Top 50 Player Stats</div>
        <div class="champ-title-row">
          <img src="{icon_url}" alt="{name} Wild Rift portrait" width="64" height="64" />
          <h1 style="font-size:2.4rem;">{name}{badges}</h1>
        </div>
        <div class="champ-tags">
          {role} <span class="sep">&middot;</span>
          {cls} <span class="sep">&middot;</span>
          {diff_word}
        </div>
      </div>
    </div>

    <div class="stats">
      <div class="stat"><div class="stat-l">Tier</div><div class="stat-v tier-{tier_css}">{tier_label}</div></div>
      <div class="stat"><div class="stat-l">Win Rate</div><div class="stat-v accent">{wr}%</div></div>
      <div class="stat"><div class="stat-l">Ceiling WR</div><div class="stat-v gold">{ceiling}%</div></div>
      <div class="stat"><div class="stat-l">Median Games</div><div class="stat-v">{median_g}</div></div>
    </div>

    <section class="block">
      <h2>{name} Win Rate &amp; Tier in Wild Rift</h2>
      <p>{name} is currently <strong>{tier_label} tier</strong> in EU Wild Rift, with a games-weighted win rate of <strong>{wr}%</strong> across the top 50 players. The highest-WR top-50 player on {name} sits at <strong>{ceiling}%</strong>. These are elite specialists, so all win rates are above 50% &mdash; the meaningful signal is the gap between champions, not the absolute number.</p>
      <p>{name}'s top players each have a median of <strong>{median_g}</strong> games tracked on the champion. That number drives the entry floor for our confidence-adjusted win rate: it filters out smurfs and gives every player a fair sample.</p>
    </section>

    <section class="block">
      <h2>Best {name} Player</h2>
      {best_section}
    </section>

    <section class="block builds">
      <span class="builds-coming">Coming soon</span>
      <h2>Best {name} Build &middot; Items &amp; Runes</h2>
      <p>The best <strong>{name} build</strong> &mdash; including the items, runes, and skill order used by EU's rank #1 {name} player &mdash; will appear here. We're collecting build data directly from in-game player profiles so the recommendation reflects what the actual top {name} player is running this patch, not a generic guide.</p>
      <p>Looking for a Wild Rift {name} build guide today? Check back after our next data refresh, or bookmark this page.</p>
    </section>

    <section class="block">
      <h2>Related {role} Champions</h2>
      <p>Other Wild Rift {role} champions tracked in the meta:</p>
      <div class="related-grid">{related_html}</div>
    </section>
  </article>

  <div class="cta">
    <h2 style="font-size:1.25rem; margin-bottom:0.4rem;">Want the live {name} leaderboard?</h2>
    <p style="color:rgba(230,236,255,0.85);">See the full top 50 {name} players, their win rates, mastery, and games played.</p>
    <a href="https://wrtruemeta.streamlit.app/Leaderboard?champion={name}">Open the live {name} leaderboard &rarr;</a>
  </div>

  <footer class="site">
    Last updated {rendered}. Questions or feedback? DM <strong style="color:var(--accent);">@generalthr4gg</strong> on Discord.<br/>
    Not affiliated with Riot Games. League of Legends &amp; Wild Rift are &copy; Riot Games, Inc.<br/>
    Methodology: top-50 confidence-adjusted win rate, twice-monthly refresh.
  </footer>
</div>
</body>
</html>"""


INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wildrift Champions — League of Legends Wildrift Stats, Win Rates &amp; Builds | WrTrueMeta</title>
<meta name="description" content="Every League of Legends Wildrift champion ranked by real EU top-50 player win rates. Click a champion for Wild Rift stats, tier, best player, and build (coming soon).">
<meta name="keywords" content="Wildrift champions, Wild Rift champions, League of Legends Wildrift champions, LoL Wildrift champion list, Wildrift champion stats, Wild Rift champion builds, Wildrift champion win rates, Wildrift champion guide">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="Wild Rift Champions — Stats, Win Rates &amp; Builds | WrTrueMeta">
<meta property="og:description" content="Every Wild Rift champion ranked by real EU top-50 player win rates.">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#070b18">
<link rel="icon" type="image/png" href="/logo.png?v=2">
<style>""" + _SHARED_HEAD_CSS + """
.champ-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.65rem; margin: 1.5rem 0; }
.ci-card { display: flex; align-items: center; gap: 0.8rem; padding: 0.7rem 0.85rem; background: var(--card); border: 1px solid var(--border); border-radius: 12px; text-decoration: none; color: var(--text); transition: border-color 0.15s, transform 0.15s; }
.ci-card:hover { border-color: rgba(74,144,255,0.35); transform: translateY(-2px); }
.ci-card img { border-radius: 50%; border: 1px solid rgba(255,255,255,0.1); }
.ci-meta { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.ci-name { font-weight: 700; font-size: 0.95rem; overflow: hidden; text-overflow: ellipsis; }
.ci-tier { font-size: 0.7rem; font-weight: 800; letter-spacing: 0.05em; padding: 0.1rem 0.4rem; border-radius: 4px; align-self: flex-start; margin-top: 0.2rem; color: #fff; }
.ci-tier.tier-tier-god { background: linear-gradient(135deg, #ffd24a, #e53916); }
.ci-tier.tier-tier-s { background: linear-gradient(135deg, #ff8c42, #ff6b1a); }
.ci-tier.tier-tier-a { background: linear-gradient(135deg, #ffd14a, #f5b800); color: #2a1500; }
.ci-tier.tier-tier-b { background: linear-gradient(135deg, #4a90ff, #2b6ad6); }
.ci-tier.tier-tier-c { background: linear-gradient(135deg, #8a92a8, #5a6378); }
.ci-tier.tier-tier-ass { background: linear-gradient(135deg, #4a5066, #2a2e3e); color: #aeb4c6; }
.ci-wr { color: var(--accent); font-weight: 800; font-size: 1rem; flex-shrink: 0; }
</style>
</head>
<body>
<div class="container">
  <header class="brand">
    <a href="/" rel="home"><img src="/logo.png?v=2" alt="WrTrueMeta logo" /></a>
    <nav>
      <a href="/">Home</a>
      <a href="https://wrtruemeta.streamlit.app/Tier_List">Tier List</a>
      <a href="https://wrtruemeta.streamlit.app/Leaderboard">Leaderboards</a>
      <a href="https://wrtruemeta.streamlit.app" style="color:var(--accent);">Open App &rarr;</a>
    </nav>
  </header>

  <h1>Wild Rift <span class="accent">Champions</span></h1>
  <p class="lead">Every Wild Rift champion tracked on EU, with real top-50 player win rates. Click any champion for tier, ceiling, best player, and build info. Updated <span class="pill">twice a month</span>.</p>
  <p style="color:var(--muted); font-size: 0.9rem;">{n} champions &middot; last updated {rendered}</p>

  <div class="champ-grid">{cards}</div>

  <footer class="site">
    Questions or feedback? DM <strong style="color:var(--accent);">@generalthr4gg</strong> on Discord.<br/>
    Not affiliated with Riot Games. League of Legends &amp; Wild Rift are &copy; Riot Games, Inc.
  </footer>
</div>
</body>
</html>"""


BUILDS_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wildrift Champion Builds — League of Legends Wildrift Items, Runes &amp; Skill Order | WrTrueMeta</title>
<meta name="description" content="League of Legends Wildrift champion builds based on real EU top-50 player data. See exactly which items, runes, and skill order the rank #1 Wild Rift player on each champion runs.">
<meta name="keywords" content="Wildrift builds, Wild Rift builds, League of Legends Wildrift builds, LoL Wildrift builds, Wildrift champion builds, Wildrift item build, Wildrift runes, Wild Rift runes, best Wildrift build, Wildrift S21 build, WR builds, Wildrift item guide">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="Wild Rift Champion Builds — Best Items, Runes &amp; Skill Order">
<meta property="og:description" content="Wild Rift champion builds based on real EU top-50 player data.">
<meta property="og:url" content="{canonical}">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#070b18">
<link rel="icon" type="image/png" href="/logo.png?v=2">
<style>""" + _SHARED_HEAD_CSS + """
.hero { background: linear-gradient(135deg, rgba(74,144,255,0.15), rgba(212,166,74,0.05)); border: 1px solid rgba(74,144,255,0.3); border-radius: 16px; padding: 1.75rem 2rem; margin-bottom: 1.5rem; }
.coming-pill { display: inline-block; color: var(--gold); font-weight: 700; padding: 0.3rem 0.8rem; border: 1px solid rgba(212,166,74,0.45); border-radius: 999px; font-size: 0.85rem; background: rgba(212,166,74,0.12); margin-bottom: 0.8rem; }
.teaser-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 0.6rem; margin-top: 1.2rem; }
.b-tile { display: flex; flex-direction: column; align-items: center; padding: 0.75rem; background: var(--card); border: 1px solid var(--border); border-radius: 12px; text-decoration: none; color: var(--text); transition: border-color 0.15s, transform 0.15s; }
.b-tile:hover { border-color: rgba(74,144,255,0.35); transform: translateY(-2px); }
.b-tile img { width: 56px; height: 56px; border-radius: 50%; border: 1px solid rgba(255,255,255,0.1); }
.b-tile span { font-size: 0.82rem; margin-top: 0.4rem; font-weight: 600; }
section.block { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 1.25rem 1.5rem; margin: 1.5rem 0; }
section.block h2 { font-size: 1.3rem; font-weight: 800; margin-bottom: 0.7rem; }
section.block p, section.block li { color: rgba(230,236,255,0.88); margin-bottom: 0.5rem; }
section.block ul { padding-left: 1.5rem; }
</style>
</head>
<body>
<div class="container">
  <header class="brand">
    <a href="/" rel="home"><img src="/logo.png?v=2" alt="WrTrueMeta logo" /></a>
    <nav>
      <a href="/">Home</a>
      <a href="https://wrtruemeta.streamlit.app/Tier_List">Tier List</a>
      <a href="https://wrtruemeta.streamlit.app/Champions">Champions</a>
      <a href="https://wrtruemeta.streamlit.app" style="color:var(--accent);">Open App &rarr;</a>
    </nav>
  </header>

  <div class="hero">
    <div class="coming-pill">Coming soon</div>
    <h1>Wild Rift <span class="accent">Champion Builds</span></h1>
    <p class="lead">The best Wild Rift builds &mdash; items, runes, and skill order &mdash; pulled directly from each champion's rank #1 player on EU. Not generic guides; the actual loadouts the top players are winning with.</p>
    <p style="color:var(--muted); font-size: 0.9rem;">Last updated {rendered}. Builds launch on the next data refresh.</p>
  </div>

  <section class="block">
    <h2>How WrTrueMeta builds will work</h2>
    <p>Most Wild Rift build guides are written from theorycraft or pulled from a small public sample. We do it differently: we already track the top 50 players on every champion. The builds page will surface the actual itemization, rune choice, and skill-priority order each rank #1 player is running &mdash; pulled directly from their in-game profile.</p>
    <ul>
      <li><strong>Real data, not opinion</strong> &mdash; every build comes from a player demonstrably at the top of the EU ladder on that champion.</li>
      <li><strong>One canonical build per champion, plus alternates</strong> when the rank #2 / #3 players diverge.</li>
      <li><strong>Refreshed twice a month</strong>, same cadence as our tier list and win rates.</li>
      <li><strong>Per-champion pages</strong> with the build inline, so you can read it where you're already checking the win rate.</li>
    </ul>
  </section>

  <section class="block">
    <h2>Champions to feature first</h2>
    <p>We'll ship builds for the highest-traffic champions first. Click any champion to see their tier, win rate, and the build placeholder where the loadout will land:</p>
    <div class="teaser-grid">{teasers}</div>
  </section>

  <footer class="site">
    Questions or feedback? DM <strong style="color:var(--accent);">@generalthr4gg</strong> on Discord.<br/>
    Not affiliated with Riot Games. League of Legends &amp; Wild Rift are &copy; Riot Games, Inc.<br/>
    Want a specific champion's build prioritised? <a href="/">Let us know on the homepage</a>.
  </footer>
</div>
</body>
</html>"""


# ---------- Homepage ----------------------------------------------------

def build_homepage(df, summary) -> str:
    """Real launch homepage — static, SEO-strong, links into the live app.

    Shows hero + 3 teaser stats (top pick, biggest mover, top OTP) + nav
    cards into the four key pages (tier list, champions, builds, app).
    """
    from web.data_loader import (
        pick_of_the_patch as _potp,
        skill_spread as _spread,
        multi_champion_mains as _mm,
    )

    today = date.today()
    rendered = f"{today.strftime('%B')} {today.day}, {today.year}"

    n_champs = int(summary["weighted_winrate"].notna().sum())
    n_players = int(len(df))

    potp = _potp(df)
    top_pick = potp["champion"] if potp else "—"
    top_pick_wr = f"{potp['weighted_winrate']:.1f}%" if potp else "—"

    spread = _spread(df, summary)
    spread = spread[spread["n_players"] >= 20]
    top_spread = spread.iloc[0] if not spread.empty else None
    spread_name = str(top_spread["champion"]) if top_spread is not None else "—"
    spread_val = f"{top_spread['skill_spread']:.1f}pts" if top_spread is not None else "—"

    best_otp_df = summary[summary["is_otp"]].sort_values("weighted_winrate", ascending=False)
    best_otp_name = str(best_otp_df.iloc[0]["champion"]) if not best_otp_df.empty else "—"
    best_otp_wr = f"{best_otp_df.iloc[0]['weighted_winrate']:.1f}%" if not best_otp_df.empty else "—"

    n_mains = len(_mm(df, min_champions=3))

    return _render(HOMEPAGE_TEMPLATE, {
        "rendered": rendered,
        "n_champs": n_champs,
        "n_players": f"{n_players:,}",
        "n_mains": n_mains,
        "top_pick": escape(top_pick),
        "top_pick_slug": champion_to_slug(top_pick) if potp else "",
        "top_pick_wr": top_pick_wr,
        "top_pick_icon": icon_url(top_pick) if potp else "",
        "spread_name": escape(spread_name),
        "spread_slug": champion_to_slug(spread_name) if top_spread is not None else "",
        "spread_val": spread_val,
        "spread_icon": icon_url(spread_name) if top_spread is not None else "",
        "otp_name": escape(best_otp_name),
        "otp_slug": champion_to_slug(best_otp_name) if not best_otp_df.empty else "",
        "otp_wr": best_otp_wr,
        "otp_icon": icon_url(best_otp_name) if not best_otp_df.empty else "",
    })


HOMEPAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WrTrueMeta — Wildrift Tier List, Win Rates &amp; Meta Tracker | League of Legends Wildrift</title>
<meta name="description" content="Real League of Legends Wildrift win rates from the top 50 players on every champion. Wildrift tier list, leaderboards, best players, role &amp; class meta — updated twice a month. EU live.">
<meta name="keywords" content="Wildrift tier list, Wild Rift tier list, League of Legends Wildrift, LoL Wildrift, Wildrift meta, Wildrift win rates, Wildrift champion stats, best Wildrift champions, Wildrift leaderboard, WR meta, Wildrift EU, Wildrift S21">
<meta name="author" content="WrTrueMeta">
<meta name="robots" content="index, follow, max-image-preview:large">
<link rel="canonical" href="https://wrtruemeta.com/">
<meta property="og:site_name" content="WrTrueMeta">
<meta property="og:title" content="WrTrueMeta — Wildrift Tier List, Win Rates &amp; Meta Tracker">
<meta property="og:description" content="Real League of Legends Wildrift win rates from the top 50 players on every champion. Tier list, leaderboards, best players.">
<meta property="og:image" content="https://wrtruemeta.com/landing_bg.jpg">
<meta property="og:image:width" content="1920">
<meta property="og:image:height" content="1080">
<meta property="og:url" content="https://wrtruemeta.com/">
<meta property="og:type" content="website">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="WrTrueMeta — Wildrift Tier List &amp; Meta Tracker">
<meta name="twitter:description" content="Real Wildrift win rates from the top 50 players of every champion. Tier list, leaderboards, best players.">
<meta name="twitter:image" content="https://wrtruemeta.com/landing_bg.jpg">
<meta name="theme-color" content="#070b18">
<link rel="icon" type="image/png" href="/logo.png?v=2">
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "@id": "https://wrtruemeta.com/#website",
  "url": "https://wrtruemeta.com/",
  "name": "WrTrueMeta",
  "description": "Wildrift tier list and meta tracker built from real top-50 player data."
}
</script>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #070b18; --card: #121a30; --card-2: #1a2240;
  --border: rgba(255,255,255,0.07); --text: #e6ecff; --muted: #8a92a8;
  --accent: #4a90ff; --gold: #ffd76e;
}
html { scroll-behavior: smooth; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  color: var(--text); line-height: 1.55;
  background:
    radial-gradient(circle at 15% -10%, rgba(74,144,255,0.12), transparent 55%),
    radial-gradient(circle at 85% 110%, rgba(74,144,255,0.08), transparent 55%),
    var(--bg);
  min-height: 100vh;
}
.page { max-width: 1180px; margin: 0 auto; padding: 1.5rem 1.25rem 4rem; }

/* Header / nav */
.hdr {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 2.5rem; padding: 0.4rem 0.5rem;
}
.brand img { height: 64px; width: auto; display: block; filter: drop-shadow(0 3px 10px rgba(0,0,0,0.6)); }
.hdr-nav { display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.hdr-nav a {
  color: var(--muted); text-decoration: none; font-size: 0.92rem; font-weight: 600;
  padding: 0.55rem 0.95rem; border-radius: 9px; transition: color 0.15s, background 0.15s;
}
.hdr-nav a:hover { color: var(--text); background: rgba(255,255,255,0.05); }
.hdr-nav .hdr-cta {
  background: var(--accent); color: #fff; padding: 0.55rem 1.1rem;
}
.hdr-nav .hdr-cta:hover { background: #5fa0ff; color: #fff; }

/* Mobile nav — hidden on desktop, takes over the right side at narrow widths */
.hdr-mobile { display: none; align-items: center; gap: 0.5rem; }
.hdr-mobile .hdr-cta {
  background: var(--accent); color: #fff; padding: 0.55rem 0.95rem;
  border-radius: 9px; font-weight: 700; font-size: 0.88rem; text-decoration: none;
}
.hdr-menu { position: relative; }
.hdr-menu summary {
  list-style: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  width: 42px; height: 42px;
  border-radius: 10px;
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border);
  color: var(--text);
  transition: background 0.15s, border-color 0.15s;
}
.hdr-menu summary::-webkit-details-marker { display: none; }
.hdr-menu summary:hover { background: rgba(255,255,255,0.1); border-color: rgba(74,144,255,0.4); }
.hdr-menu[open] summary { background: rgba(74,144,255,0.12); border-color: rgba(74,144,255,0.45); color: var(--accent); }
.hdr-menu-panel {
  position: absolute; right: 0; top: calc(100% + 0.5rem);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 0.4rem;
  min-width: 200px;
  display: flex; flex-direction: column; gap: 0.15rem;
  box-shadow: 0 12px 32px rgba(0,0,0,0.55);
  z-index: 100;
}
.hdr-menu-panel a {
  padding: 0.7rem 0.9rem; border-radius: 8px;
  color: var(--text); text-decoration: none;
  font-weight: 600; font-size: 0.95rem;
  transition: background 0.15s, color 0.15s;
}
.hdr-menu-panel a:hover { background: rgba(74,144,255,0.1); color: var(--accent); }

/* Hero */
.hero { text-align: center; padding: 2rem 0 2.5rem; }
.eyebrow {
  color: var(--accent); font-size: 0.78rem; font-weight: 800;
  letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 1.25rem;
}
.hero h1 {
  font-size: clamp(2rem, 5vw, 3.4rem); font-weight: 800; letter-spacing: -0.02em;
  line-height: 1.08; margin: 0 auto 1.25rem; max-width: 880px;
}
.hero h1 .accent { color: var(--accent); }
.hero p.lead {
  color: rgba(230, 236, 255, 0.9); font-size: clamp(1rem, 2vw, 1.15rem);
  max-width: 720px; margin: 0 auto 2rem; line-height: 1.55;
}
.hero-cta {
  display: flex; gap: 0.8rem; justify-content: center; flex-wrap: wrap; margin-bottom: 1.5rem;
}
.btn {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.85rem 1.5rem; border-radius: 11px; font-weight: 700;
  font-size: 1rem; text-decoration: none; transition: transform 0.15s, background 0.15s;
}
.btn.primary { background: var(--accent); color: #fff; box-shadow: 0 8px 24px rgba(74,144,255,0.3); }
.btn.primary:hover { background: #5fa0ff; transform: translateY(-2px); }
.btn.ghost { background: rgba(255,255,255,0.05); color: var(--text); border: 1px solid rgba(255,255,255,0.12); }
.btn.ghost:hover { background: rgba(255,255,255,0.08); transform: translateY(-2px); }
.hero-meta { color: var(--muted); font-size: 0.92rem; }
.hero-meta strong { color: var(--text); }

/* Teaser cards */
.teaser-grid {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem; margin-bottom: 3rem;
}
.teaser-card {
  background: linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 100%), rgba(12,18,38,0.62);
  border: 1px solid var(--border); border-radius: 14px;
  padding: 1.25rem 1.4rem; text-decoration: none; color: var(--text);
  transition: border-color 0.18s, transform 0.18s;
  backdrop-filter: blur(14px) saturate(120%);
  -webkit-backdrop-filter: blur(14px) saturate(120%);
}
.teaser-card:hover { border-color: rgba(74,144,255,0.4); transform: translateY(-2px); }
.teaser-tag {
  color: var(--muted); font-size: 0.66rem; font-weight: 800;
  letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 0.8rem;
}
.teaser-row { display: flex; align-items: center; gap: 0.9rem; }
.teaser-row img { border-radius: 50%; border: 2px solid rgba(255,255,255,0.1); }
.teaser-name { font-weight: 700; font-size: 1.1rem; }
.teaser-val { font-size: 1.5rem; font-weight: 800; line-height: 1.1; margin-top: 0.1rem; }
.teaser-val.accent { color: var(--accent); }
.teaser-val.gold { color: var(--gold); }
.teaser-sub { color: var(--muted); font-size: 0.72rem; margin-top: 0.15rem; }

/* Explore section */
.explore { margin-bottom: 3.5rem; }
.explore h2, .why h2 {
  font-size: clamp(1.4rem, 3vw, 1.9rem); font-weight: 800;
  text-align: center; margin-bottom: 1.5rem; letter-spacing: -0.01em;
}
.explore h2 .accent, .why h2 .accent { color: var(--accent); }
.explore-grid {
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 0.9rem;
}
.explore-card {
  background: rgba(12,18,38,0.55); border: 1px solid var(--border); border-radius: 12px;
  padding: 1.25rem 1.2rem; text-decoration: none; color: var(--text);
  transition: border-color 0.18s, transform 0.18s;
}
.explore-card:hover { border-color: rgba(74,144,255,0.4); transform: translateY(-2px); }
.explore-icon { color: var(--accent); font-size: 1.3rem; margin-bottom: 0.5rem; }
.explore-title { font-weight: 700; font-size: 1.1rem; margin-bottom: 0.35rem; }
.explore-title .soon {
  display: inline-block; background: rgba(212,166,74,0.15); color: var(--gold);
  border: 1px solid rgba(212,166,74,0.4);
  font-size: 0.6rem; padding: 0.05rem 0.4rem; border-radius: 999px;
  font-weight: 700; vertical-align: middle; margin-left: 0.3rem; letter-spacing: 0.05em;
}
.explore-desc { color: var(--muted); font-size: 0.88rem; line-height: 1.5; }

/* Why section */
.why { margin-bottom: 3rem; }
.why-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.5rem; }
.why-h { color: var(--accent); font-weight: 800; font-size: 1rem; margin-bottom: 0.4rem; letter-spacing: 0.01em; }
.why-grid p { color: rgba(230,236,255,0.82); font-size: 0.92rem; line-height: 1.6; }

/* Footer */
.ftr {
  color: var(--muted); font-size: 0.78rem; text-align: center;
  padding-top: 2rem; line-height: 1.7;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.ftr a { color: var(--accent); text-decoration: none; }

/* Responsive */
@media (max-width: 900px) {
  .teaser-grid { grid-template-columns: 1fr; }
  .explore-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .why-grid { grid-template-columns: 1fr; gap: 1.25rem; }
}
/* Swap to the mobile nav at narrow viewports — the desktop pill-row of 4
   links was wrapping/cramping below 720px and there was no affordance to
   indicate the extra items were even there. */
@media (max-width: 720px) {
  .hdr-nav { display: none; }
  .hdr-mobile { display: flex; }
}

@media (max-width: 600px) {
  .page { padding: 1rem 0.65rem 3rem; }
  .hdr { gap: 0.75rem; padding: 0.4rem 0.25rem; }
  .brand img { height: 52px; }
  .hdr-mobile .hdr-cta { padding: 0.5rem 0.8rem; font-size: 0.82rem; }
  .hdr-menu summary { width: 38px; height: 38px; }
  .hero { padding: 1rem 0 1.5rem; }
  .hero-cta { flex-direction: column; align-items: stretch; }
  .btn { justify-content: center; }
  .explore-grid { grid-template-columns: 1fr; }
}

img { max-width: 100%; height: auto; }
</style>
</head>
<body>
<div class="page">
  <header class="hdr">
    <a class="brand" href="/" rel="home"><img src="/logo.png?v=2" alt="WrTrueMeta — Wildrift meta tracker" /></a>

    <!-- Desktop nav (hidden on mobile) -->
    <nav class="hdr-nav">
      <a href="https://wrtruemeta.streamlit.app/Tier_List">Tier List</a>
      <a href="https://wrtruemeta.streamlit.app/Champions">Champions</a>
      <a href="https://wrtruemeta.streamlit.app/Leaderboard">Leaderboards</a>
      <a class="hdr-cta" href="https://wrtruemeta.streamlit.app">Open App &rarr;</a>
    </nav>

    <!-- Mobile nav: keep primary CTA visible, drop everything else into a hamburger -->
    <div class="hdr-mobile">
      <a class="hdr-cta" href="https://wrtruemeta.streamlit.app">Open App &rarr;</a>
      <details class="hdr-menu">
        <summary aria-label="Menu">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round">
            <line x1="3" y1="6" x2="21" y2="6"/>
            <line x1="3" y1="12" x2="21" y2="12"/>
            <line x1="3" y1="18" x2="21" y2="18"/>
          </svg>
        </summary>
        <div class="hdr-menu-panel">
          <a href="https://wrtruemeta.streamlit.app/Tier_List">Tier List</a>
          <a href="https://wrtruemeta.streamlit.app/Champions">Champions</a>
          <a href="https://wrtruemeta.streamlit.app/Leaderboard">Leaderboards</a>
          <a href="https://wrtruemeta.streamlit.app/Methodology">Methodology</a>
        </div>
      </details>
    </div>
  </header>

  <section class="hero">
    <div class="eyebrow">EU Top 50 Player Data &middot; Updated {rendered}</div>
    <h1>The <span class="accent">Wildrift</span> tier list built from real top-50 player win rates.</h1>
    <p class="lead">
      Every <strong>League of Legends Wildrift</strong> champion ranked by the
      games-weighted win rate of their elite players. No opinions, no aggregated
      averages &mdash; just the actual climbers, with Bayesian-shrunk stats so
      one lucky game can&rsquo;t skew a champion&rsquo;s tier.
    </p>
    <div class="hero-cta">
      <a class="btn primary" href="https://wrtruemeta.streamlit.app">Open the Live App &rarr;</a>
      <a class="btn ghost" href="https://wrtruemeta.streamlit.app/Tier_List">Jump to Tier List &rarr;</a>
    </div>
    <div class="hero-meta">
      <strong>{n_champs}</strong> champions tracked &nbsp;&middot;&nbsp;
      <strong>{n_players}</strong> top-50 player records &nbsp;&middot;&nbsp;
      <strong>{n_mains}</strong> multi-champion mains identified
    </div>
  </section>

  <section class="teaser-grid">
    <a class="teaser-card" href="https://wrtruemeta.streamlit.app/Leaderboard?champion={top_pick}">
      <div class="teaser-tag">Top Pick This Patch</div>
      <div class="teaser-row">
        <img src="{top_pick_icon}" alt="{top_pick}" loading="lazy" width="56" height="56" />
        <div>
          <div class="teaser-name">{top_pick}</div>
          <div class="teaser-val accent">{top_pick_wr}</div>
          <div class="teaser-sub">games-weighted win rate</div>
        </div>
      </div>
    </a>
    <a class="teaser-card" href="https://wrtruemeta.streamlit.app/Leaderboard?champion={spread_name}">
      <div class="teaser-tag">Highest Skill Ceiling</div>
      <div class="teaser-row">
        <img src="{spread_icon}" alt="{spread_name}" loading="lazy" width="56" height="56" />
        <div>
          <div class="teaser-name">{spread_name}</div>
          <div class="teaser-val gold">{spread_val}</div>
          <div class="teaser-sub">ceiling vs. average top-50</div>
        </div>
      </div>
    </a>
    <a class="teaser-card" href="https://wrtruemeta.streamlit.app/Leaderboard?champion={otp_name}">
      <div class="teaser-tag">Best OTP Champion</div>
      <div class="teaser-row">
        <img src="{otp_icon}" alt="{otp_name}" loading="lazy" width="56" height="56" />
        <div>
          <div class="teaser-name">{otp_name}</div>
          <div class="teaser-val accent">{otp_wr}</div>
          <div class="teaser-sub">one-trick win rate</div>
        </div>
      </div>
    </a>
  </section>

  <section class="explore">
    <h2>Explore <span class="accent">League of Legends Wildrift</span> meta</h2>
    <div class="explore-grid">
      <a class="explore-card" href="https://wrtruemeta.streamlit.app/Tier_List">
        <div class="explore-icon">&#9650;</div>
        <div class="explore-title">Tier List</div>
        <div class="explore-desc">GOD to Ass tiers built from real top-50 player win rates. Filter by role with adaptive cutoffs.</div>
      </a>
      <a class="explore-card" href="https://wrtruemeta.streamlit.app/Champions">
        <div class="explore-icon">&#10070;</div>
        <div class="explore-title">All Champions</div>
        <div class="explore-desc">Every Wildrift champion with full stats, best player, and a per-champion landing page.</div>
      </a>
      <a class="explore-card" href="https://wrtruemeta.streamlit.app/Leaderboard">
        <div class="explore-icon">&#10084;</div>
        <div class="explore-title">Leaderboards</div>
        <div class="explore-desc">Top 50 EU players for every champion, sortable by rank, mastery, win rate, or games.</div>
      </a>
      <a class="explore-card" href="https://wrtruemeta.streamlit.app/Methodology">
        <div class="explore-icon">&#9889;</div>
        <div class="explore-title">Methodology</div>
        <div class="explore-desc">How the confidence-adjusted win rates, Bayesian shrinkage, and Wilson best-player scores actually work.</div>
      </a>
    </div>
  </section>

  <section class="why">
    <h2>Why WrTrueMeta is different</h2>
    <div class="why-grid">
      <div>
        <div class="why-h">Real player data, not aggregates</div>
        <p>Every win rate comes from the actual top 50 EU players on the champion &mdash; their tracked games, scraped from the live game. Most Wildrift sites pool everyone, which means a feeding silver Jinx drags her ranking down. We don&rsquo;t.</p>
      </div>
      <div>
        <div class="why-h">Bayesian shrinkage</div>
        <p>Small-sample win rates get pulled toward each champion&rsquo;s prior, so a 10-game 70% smurf doesn&rsquo;t outrank a 400-game 59% main. The methodology is explained in full on the app.</p>
      </div>
      <div>
        <div class="why-h">Honest about uncertainty</div>
        <p>Every page shows sample sizes. Champions with few scraped players are flagged. The confidence-adjusted win rate uses the Wilson lower bound, so &ldquo;best player&rdquo; means demonstrably best, not luckily best.</p>
      </div>
    </div>
  </section>

  <footer class="ftr">
    Questions or feedback? DM <strong style="color:var(--accent);">@generalthr4gg</strong> on Discord.<br/>
    Not affiliated with Riot Games. League of Legends &amp; Wildrift are &copy; Riot Games, Inc.<br/>
    Champion artwork via <a href="https://developer.riotgames.com/docs/lol#data-dragon" target="_blank" rel="noopener">DDragon</a>.
  </footer>
</div>
</body>
</html>"""


# ---------- Top-level driver --------------------------------------------

def main() -> None:
    df = load_leaderboard()
    if df.empty:
        raise SystemExit("data/winrates.csv is empty — scrape some champions first.")
    summary = champion_summary(df)

    # 1) Tier list page
    html = build()
    OUT_PATH.write_text(html, encoding="utf-8", newline="\n")
    print(f"wrote {OUT_PATH.name} ({OUT_PATH.stat().st_size // 1024} KB)")

    # 2) Champion directory
    idx_path = ROOT / "landing" / "champions.html"
    idx_path.write_text(build_champion_index(summary), encoding="utf-8", newline="\n")
    print(f"wrote {idx_path.name} ({idx_path.stat().st_size // 1024} KB)")

    # 3) Per-champion pages
    champ_dir = ROOT / "landing" / "champions"
    champ_dir.mkdir(parents=True, exist_ok=True)
    n_champ = 0
    for _, c in summary.iterrows():
        if pd.isna(c["weighted_winrate"]):
            continue
        html = build_champion_page(c.to_dict(), df, summary)
        slug = champion_to_slug(str(c["champion"]))
        (champ_dir / f"{slug}.html").write_text(html, encoding="utf-8", newline="\n")
        n_champ += 1
    print(f"wrote {n_champ} champion pages in landing/champions/")

    # 4) Builds landing page
    builds_path = ROOT / "landing" / "builds.html"
    builds_path.write_text(build_builds_page(summary), encoding="utf-8", newline="\n")
    print(f"wrote {builds_path.name} ({builds_path.stat().st_size // 1024} KB)")

    # 5) Launch homepage — replaces the coming-soon at landing/index.html
    home_path = ROOT / "landing" / "index.html"
    home_path.write_text(build_homepage(df, summary), encoding="utf-8", newline="\n")
    print(f"wrote {home_path.name} ({home_path.stat().st_size // 1024} KB)")

    # 6) Sitemap.xml
    _write_sitemap(summary)
    print("wrote sitemap.xml")


def _write_sitemap(summary) -> None:
    today = date.today().isoformat()
    urls = [
        ("https://wrtruemeta.com/", "1.0"),
        ("https://wrtruemeta.com/tier-list", "0.95"),
        ("https://wrtruemeta.com/champions", "0.9"),
        ("https://wrtruemeta.com/builds", "0.85"),
    ]
    for _, c in summary.iterrows():
        if pd.isna(c["weighted_winrate"]):
            continue
        slug = champion_to_slug(str(c["champion"]))
        urls.append((f"https://wrtruemeta.com/champions/{slug}", "0.7"))

    body = "\n".join(
        f"  <url><loc>{u}</loc><changefreq>weekly</changefreq>"
        f"<lastmod>{today}</lastmod><priority>{p}</priority></url>"
        for u, p in urls
    )
    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )
    (ROOT / "landing" / "sitemap.xml").write_text(sitemap, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
