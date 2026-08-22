"""Build the "best and worst champions in EU + NA" slide for TikTok/Reddit.

Generated rather than hand-written so every number on the image comes straight
out of site.json and site_na.json -- a slide that gets screenshotted is the
worst place to discover a typo.

    python scripts/make_slide_global_top_bottom.py

Writes web-next/public/global_top_bottom.html at 1600x1000 in the house style
of movers_slide.html. Open it on the dev server (or prod) at
/global_top_bottom.html and capture the slide at full size.

THE NUMBER: Global is the plain average of the EU and NA shrunk win rates,
the same blend the shorts use. Both regions are the same measurement (our
own top-50 scrape, the same wrOffset, the same 50.0 mean), so averaging them
is clean. Each card shows the blend big and the two regional numbers small,
so a viewer can see at a glance when EU and NA disagree.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web-next" / "src" / "data"
OUT = ROOT / "web-next" / "public" / "global_top_bottom.html"

SHOWN = 5

# site.json points a few champions at a custom local image whose crop hides
# the face at card size; the slide wants the base loading art for those.
BASE_ART = {
    "hecarim": "https://ddragon.leagueoflegends.com/cdn/img/champion/loading/Hecarim_0.jpg",
}


def load() -> tuple[list[dict], str]:
    eu = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    na = json.loads((DATA / "site_na.json").read_text(encoding="utf-8"))
    na_by = {c["slug"]: c for c in na["champions"] if c.get("wr") is not None}
    merged = []
    for c in eu["champions"]:
        n = na_by.get(c["slug"])
        if c.get("wr") is None or n is None:
            continue
        merged.append({"name": c["name"], "slug": c["slug"],
                       "splash": BASE_ART.get(c["slug"]) or c.get("splash") or "",
                       "eu": c["wr"], "na": n["wr"], "global": round((c["wr"] + n["wr"]) / 2, 1)})
    stat_rules = json.loads((DATA / "stat_rules.json").read_text(encoding="utf-8"))
    patch = eu.get("patch") or stat_rules.get("targetPatch", "")
    return merged, patch


def card(m: dict, rank: int, up: bool) -> str:
    tone = "up" if up else "down"
    return f"""
      <div class="card {tone}">
        <div class="art" style="background-image:url('{m['splash']}')"></div>
        <div class="fade"></div>
        <div class="rank">#{rank}</div>
        <div class="delta">{m['global']:.1f}%</div>
        <div class="foot">
          <div class="name">{m['name']}</div>
          <div class="wr">EU {m['eu']:.1f} · NA {m['na']:.1f}</div>
        </div>
      </div>"""


def main() -> None:
    merged, patch = load()
    best = sorted(merged, key=lambda m: (-m["global"], m["name"]))[:SHOWN]
    worst = sorted(merged, key=lambda m: (m["global"], m["name"]))[:SHOWN]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Best & Worst Champions · EU + NA · Patch {patch}</title>
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
  .art {{ position: absolute; inset: 0; background-size: cover; background-position: top center; }}
  .fade {{ position: absolute; inset: 0;
    background: linear-gradient(180deg, rgba(5,8,15,0.05) 40%, rgba(5,8,15,0.42) 72%, rgba(5,8,15,0.9) 100%); }}
  .rank {{
    position: absolute; top: 10px; left: 10px;
    font-size: 22px; font-weight: 900; padding: 3px 11px; border-radius: 999px;
    background: rgba(5,8,15,0.62); color: #e8edf6; border: 1px solid rgba(255,255,255,0.22);
    text-shadow: 0 1px 6px rgba(0,0,0,0.5); backdrop-filter: blur(8px);
  }}
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
      <h1>Patch {patch} · Best &amp; Worst Champions</h1>
      <div class="sub">EU + NA win rate · the 50 best players on every champion</div>
    </div>
    <div class="site">wrtruemeta.com</div>
  </div>
  <div class="rows">
    <div class="row">
      <div class="tag up">Best</div>
      <div class="cards">{''.join(card(m, i + 1, True) for i, m in enumerate(best))}</div>
    </div>
    <div class="row">
      <div class="tag down">Worst</div>
      <div class="cards">{''.join(card(m, i + 1, False) for i, m in enumerate(worst))}</div>
    </div>
  </div>
</div>
</body>
</html>
"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    print("best: ", ", ".join(f"{m['name']} {m['global']}" for m in best))
    print("worst:", ", ".join(f"{m['name']} {m['global']}" for m in worst))


if __name__ == "__main__":
    main()
