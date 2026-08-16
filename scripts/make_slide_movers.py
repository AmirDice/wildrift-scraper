"""Build the "biggest movers" slide for Reddit.

Generated rather than hand-written so every number on the image comes straight
out of cn_movers.json -- a slide that gets screenshotted onto Reddit is the
worst place to discover a typo.

    python scripts/make_slide_movers.py

Writes web-next/public/movers_slide.html at 1600x1000, matching the house
style of region_split_2026.html. Open it on the dev server (or prod) at
/movers_slide.html and capture the slide at full size.

DESIGN: the ask was "least text as possible, easy to read on Reddit". So the
champions ARE the slide: ten loading-art portraits, five rising on top, five
falling below, each carrying exactly two facts -- the delta, big, and the win
rate it landed on, small. Everything else is one header line and the site
name. Reddit sees faces and green/red numbers before it reads a single word,
which is the whole trick.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web-next" / "src" / "data"
OUT = ROOT / "web-next" / "public" / "movers_slide.html"

SHOWN = 5
MIN_PICK = 0.5  # match lib/movers.ts: swings on unplayed champions are noise


def date_label(raw: str) -> str:
    try:
        return datetime.strptime(raw, "%Y%m%d").strftime("%b %d").replace(" 0", " ")
    except ValueError:
        return raw


def load() -> tuple[dict, dict[str, dict]]:
    movers = json.loads((DATA / "cn_movers.json").read_text(encoding="utf-8"))
    site = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    by_slug = {c["slug"]: c for c in site["champions"]}
    return movers, by_slug


def card(m: dict, by_slug: dict[str, dict], up: bool) -> str:
    champ = by_slug.get(m["slug"], {})
    art = champ.get("splash") or ""
    tone = "up" if up else "down"
    delta = f"+{m['delta']}" if m["delta"] > 0 else f"{m['delta']}"
    return f"""
      <div class="card {tone}">
        <div class="art" style="background-image:url('{art}')"></div>
        <div class="fade"></div>
        <div class="delta">{delta}</div>
        <div class="foot">
          <div class="name">{m['name']}</div>
          <div class="wr">{m['newWr']:.1f}% WR</div>
        </div>
      </div>"""


def main() -> None:
    movers, by_slug = load()
    pool = [m for m in movers["champions"] if m["pickRate"] >= MIN_PICK]
    winners = [m for m in pool if m["delta"] > 0][:SHOWN]
    losers = [m for m in pool if m["delta"] < 0][::-1][:SHOWN]
    # cn_movers carries no patch stamp; the site's own source of truth does.
    stat_rules = json.loads((DATA / "stat_rules.json").read_text(encoding="utf-8"))
    patch = movers.get("patch") or stat_rules.get("targetPatch", "")
    before, after = date_label(movers["beforeDate"]), date_label(movers["afterDate"])
    scope = movers.get("scope", "China · Challenger")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Biggest Movers · Patch {patch}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ background: #05080f; }}
  .slide {{
    width: 1600px; height: 1000px; margin: 24px auto;
    position: relative; isolation: isolate; overflow: hidden;
    border: 1px solid rgba(255,255,255,0.10); border-radius: 22px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #e8edf6; padding: 40px 50px 26px; display: flex; flex-direction: column;
  }}
  .bg-art {{ position: absolute; inset: 0; z-index: -3; background: url(/ionia2.jpg) center / cover no-repeat; }}
  .bg-dark {{ position: absolute; inset: 0; z-index: -2;
    background: linear-gradient(180deg, rgba(7,10,18,0.5) 0%, rgba(7,10,18,0.56) 45%, rgba(7,10,18,0.6) 100%); }}
  .bg-vignette {{ position: absolute; inset: 0; z-index: -1;
    background: radial-gradient(125% 105% at 50% 45%, transparent 55%, rgba(3,5,11,0.42) 88%, rgba(3,5,11,0.62) 100%); }}

  .head {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 30px; }}
  .brand img {{ height: 30px; display: block; filter: drop-shadow(0 2px 10px rgba(0,0,0,0.6)); }}
  h1 {{ font-size: 46px; font-weight: 800; letter-spacing: -0.015em; margin-top: 6px; text-shadow: 0 2px 18px rgba(0,0,0,0.45); }}
  .sub {{ margin-top: 7px; font-size: 16px; color: #b6c1d4; text-shadow: 0 1px 10px rgba(0,0,0,0.5); }}
  .site {{ font-size: 18px; font-weight: 800; color: #7fb2ff; text-shadow: 0 1px 10px rgba(0,0,0,0.6); padding-bottom: 6px; }}

  .rows {{ display: flex; flex-direction: column; gap: 16px; margin-top: 20px; flex: 1; min-height: 0; }}
  .row {{ flex: 1; display: flex; align-items: stretch; gap: 14px; min-height: 0; }}
  .tag {{
    writing-mode: vertical-rl; transform: rotate(180deg);
    display: flex; align-items: center; justify-content: center;
    font-size: 17px; font-weight: 900; letter-spacing: 0.3em; text-transform: uppercase;
    border-radius: 14px; width: 46px; flex-shrink: 0;
  }}
  .tag.up {{ background: rgba(34,197,94,0.16); color: #4ade80; border: 1px solid rgba(74,222,128,0.35); }}
  .tag.down {{ background: rgba(239,68,68,0.14); color: #f87171; border: 1px solid rgba(248,113,113,0.35); }}

  .cards {{ flex: 1; display: grid; grid-template-columns: repeat({SHOWN}, 1fr); gap: 14px; min-height: 0; }}
  .card {{
    position: relative; overflow: hidden; border-radius: 18px;
    border: 1px solid rgba(255,255,255,0.18);
    box-shadow: 0 10px 30px -8px rgba(0,0,0,0.6);
  }}
  .card.up {{ border-color: rgba(74,222,128,0.45); }}
  .card.down {{ border-color: rgba(248,113,113,0.4); }}
  /* ddragon loading art is 308x560 with the face in the upper third; anchoring
     the crop to the top keeps every face regardless of card height. */
  .art {{ position: absolute; inset: 0; background-size: cover; background-position: top center; }}
  .fade {{ position: absolute; inset: 0;
    background: linear-gradient(180deg, rgba(5,8,15,0.05) 40%, rgba(5,8,15,0.42) 72%, rgba(5,8,15,0.9) 100%); }}
  .delta {{
    position: absolute; top: 10px; right: 10px;
    font-size: 30px; font-weight: 900; font-variant-numeric: tabular-nums;
    padding: 4px 13px; border-radius: 999px; letter-spacing: -0.01em;
    text-shadow: 0 1px 6px rgba(0,0,0,0.5); backdrop-filter: blur(8px);
  }}
  .up .delta {{ background: rgba(20,83,45,0.72); color: #6ff0a4; border: 1px solid rgba(74,222,128,0.5); }}
  .down .delta {{ background: rgba(88,18,18,0.72); color: #ff9d9d; border: 1px solid rgba(248,113,113,0.5); }}
  .foot {{ position: absolute; left: 14px; right: 14px; bottom: 11px; }}
  .name {{ font-size: 21px; font-weight: 800; letter-spacing: -0.01em; text-shadow: 0 2px 10px rgba(0,0,0,0.8); }}
  .wr {{ margin-top: 1px; font-size: 13.5px; font-weight: 600; color: #c2cde2; text-shadow: 0 1px 8px rgba(0,0,0,0.8); }}
</style>
</head>
<body>
<div class="slide">
  <div class="bg-art"></div><div class="bg-dark"></div><div class="bg-vignette"></div>
  <div class="head">
    <div>
      <div class="brand"><img src="/logo.png" alt="WrTrueMeta"></div>
      <h1>Patch {patch} · Biggest Movers</h1>
      <div class="sub">{scope} win rate · {before} → {after}</div>
    </div>
    <div class="site">wrtruemeta.com/movers</div>
  </div>
  <div class="rows">
    <div class="row">
      <div class="tag up">Rising</div>
      <div class="cards">{''.join(card(m, by_slug, True) for m in winners)}</div>
    </div>
    <div class="row">
      <div class="tag down">Falling</div>
      <div class="cards">{''.join(card(m, by_slug, False) for m in losers)}</div>
    </div>
  </div>
</div>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    print("winners:", ", ".join(f"{m['name']} +{m['delta']}" for m in winners))
    print("losers: ", ", ".join(f"{m['name']} {m['delta']}" for m in losers))


if __name__ == "__main__":
    main()
