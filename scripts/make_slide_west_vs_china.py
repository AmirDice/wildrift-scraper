"""Build the "4th in EU + NA, 110th in China" slide.

Generated rather than hand-written so every number on the image comes straight
out of site.json, site_na.json and cn.json.

    python scripts/make_slide_west_vs_china.py

Writes web-next/public/west_vs_china_2026.html at 1600x1000.

WHY RANK, NOT WIN RATE:

  The EU + NA figure is our own scrape of the 50 best players on a champion. The
  China figure is Tencent's published rate across the whole Challenger bracket.
  Those are different populations, so subtracting one win rate from the other
  compares two rulers with different markings: the EU spread runs 43.7 to 60.2
  while CN only runs 43.9 to 56.0, and a 3 point gap is not the same distance
  in each.

  Rank is unit-free. "Where does this champion sit among its peers, inside its
  own population" is a question both datasets can answer honestly, and it never
  requires the two scales to be commensurable. It is the reason this slide can
  exist at all while CN stays out of the Global win-rate blend.

  The obvious objection is that China is not a top-50 sample, so any gap is
  really a mastery effect. Tested and rejected: if that were the driver, the
  gap would track how a champion responds when the population narrows, which is
  exactly what CN's own bracket skew measures (Challenger minus Diamond+). The
  correlation is -0.12. Two weaker proxies, maxWr-minus-wr and skillSpread,
  came in at +0.06 and +0.20. The disagreement is real, not an artefact.

  Rank correlation between the two lists is +0.455: they agree in the broad
  shape and part company on the champions shown here.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web-next" / "src" / "data"
OUT = ROOT / "web-next" / "public" / "west_vs_china_2026.html"

SHOWN = 10
MIN_PLAYERS = 40


def load() -> tuple[list[dict], dict]:
    site = json.loads((DATA / "site.json").read_text(encoding="utf-8"))
    na = json.loads((DATA / "site_na.json").read_text(encoding="utf-8"))
    cn = json.loads((DATA / "cn.json").read_text(encoding="utf-8"))

    eu = {c["slug"]: c for c in site["champions"] if c.get("wr") is not None}
    nam = {c["slug"]: c for c in na["champions"] if c.get("wr") is not None}

    cnm = {}
    for c in cn["champions"]:
        bb = c["byBracket"]
        if "3" not in bb:
            continue
        # A champion whose lane moves between brackets would have its rank set
        # by a different role than the one the West figure describes.
        lanes = {bb[k]["position"] for k in ("1", "2", "3") if k in bb}
        if len(lanes) > 1:
            continue
        cnm[c["slug"]] = bb["3"]["winRate"]

    rows = []
    for slug in set(eu) & set(nam) & set(cnm):
        e, n = eu[slug], nam[slug]
        if (e.get("nPlayers") or 0) < MIN_PLAYERS or (n.get("nPlayers") or 0) < MIN_PLAYERS:
            continue
        rows.append({
            "name": e["name"], "icon": e.get("icon") or "", "role": e["role"],
            # The same EU + NA average the site's Global ranking uses.
            "west": round((e["wr"] + n["wr"]) / 2, 1),
            "cn": cnm[slug],
        })

    for i, r in enumerate(sorted(rows, key=lambda r: -r["west"]), start=1):
        r["westRank"] = i
    for i, r in enumerate(sorted(rows, key=lambda r: -r["cn"]), start=1):
        r["cnRank"] = i
    for r in rows:
        r["swing"] = r["cnRank"] - r["westRank"]   # positive = better placed in the West

    meta = {
        "n": len(rows),
        "euDate": site.get("collectedOn"), "naDate": na.get("collectedOn"),
        "cnDate": cn.get("date"),
    }
    return rows, meta


def ordinal(n: int) -> str:
    """1 -> 1st. Used in the headline, which is derived rather than typed: the
    first draft said "Seventy Second in China" and the next data refresh moved
    Hecarim to 74th, which is exactly how a slide starts lying."""
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def rankbar(west: int, china: int, total: int, colour: str) -> str:
    """Two dots on a shared 1..total track, joined, so the swing is visible."""
    w, h, pad = 128, 26, 8
    span = w - 2 * pad
    x1 = pad + (west - 1) / max(total - 1, 1) * span
    x2 = pad + (china - 1) / max(total - 1, 1) * span
    y = h / 2
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
        f'<line x1="{pad}" y1="{y}" x2="{w-pad}" y2="{y}" stroke="rgba(255,255,255,0.14)" stroke-width="3" stroke-linecap="round"/>'
        f'<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}" stroke="{colour}" stroke-width="3" stroke-linecap="round" opacity="0.75"/>'
        f'<circle cx="{x2:.1f}" cy="{y}" r="4" fill="#8b93a7"/>'
        f'<circle cx="{x1:.1f}" cy="{y}" r="4.6" fill="{colour}"/>'
        f"</svg>"
    )


def side(rows: list[dict], total: int, colour: str, cls: str, west_first: bool) -> str:
    out = []
    for r in rows:
        a, b = (r["westRank"], r["cnRank"]) if west_first else (r["cnRank"], r["westRank"])
        out.append(f"""
        <div class="row">
          <img class="ico" src="{r['icon']}" alt="">
          <div><div class="nm">{r['name']}</div><div class="ln">{r['role']}</div></div>
          <div class="ranks"><span class="hi {cls}">{a}</span><span class="sep">vs</span><span class="lo">{b}</span></div>
          <div class="track">{rankbar(r['westRank'], r['cnRank'], total, colour)}</div>
          <div class="swing {cls}">{abs(r['swing'])}</div>
        </div>""")
    return "".join(out)


def build() -> str:
    rows, meta = load()
    total = len(rows)
    ranked = sorted(rows, key=lambda r: -r["swing"])
    west_side = ranked[:SHOWN]
    china_side = ranked[-SHOWN:][::-1]
    top_w, top_c = west_side[0], china_side[0]

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<title>{ordinal(top_w["westRank"])} in EU + NA, {ordinal(top_w["cnRank"])} in China | WrTrueMeta</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ background: #05080f; }}
  .slide {{
    width: 1600px; height: 1000px; margin: 24px auto;
    position: relative; isolation: isolate; overflow: hidden;
    border: 1px solid rgba(255,255,255,0.10); border-radius: 22px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #e8edf6; padding: 42px 50px 30px; display: flex; flex-direction: column;
  }}
  /* The site's own backdrop, copied from app/layout.tsx. */
  .bg-art {{ position: absolute; inset: 0; z-index: -3; background: url(/ionia2.jpg) center / cover no-repeat; }}
  .bg-dark {{ position: absolute; inset: 0; z-index: -2;
    background: linear-gradient(180deg, rgba(7,10,18,0.46) 0%, rgba(7,10,18,0.52) 45%, rgba(7,10,18,0.56) 100%); }}
  .bg-vignette {{ position: absolute; inset: 0; z-index: -1;
    background: radial-gradient(125% 105% at 50% 45%, transparent 55%, rgba(3,5,11,0.42) 88%, rgba(3,5,11,0.62) 100%); }}

  .glass {{
    position: relative; isolation: isolate; overflow: hidden;
    background:
      linear-gradient(120deg, rgba(79,141,255,0.10), rgba(255,255,255,0.02) 40%, rgba(79,141,255,0.08) 100%),
      linear-gradient(180deg, rgba(255,255,255,0.14) 0%, rgba(255,255,255,0.045) 45%, rgba(255,255,255,0.08) 100%),
      rgba(10,14,24,0.38);
    border: 1px solid rgba(255,255,255,0.17);
    backdrop-filter: blur(26px) saturate(200%); border-radius: 18px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.35), inset 0 -1px 0 rgba(0,0,0,0.3),
      0 1px 2px rgba(0,0,0,0.3), 0 8px 28px -10px rgba(0,0,0,0.55), 0 0 26px -6px rgba(79,141,255,0.3);
  }}
  .glass::after {{
    content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    background: linear-gradient(105deg, transparent 35%, rgba(255,255,255,0.13) 48%, rgba(255,255,255,0.045) 52%, transparent 65%);
    background-size: 260% 100%; background-position: 60% 0;
  }}

  .head {{ display: flex; align-items: flex-end; justify-content: space-between; gap: 30px; }}
  .brand {{ font-size: 20px; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; color: #4f8dff; }}
  .brand span {{ color: #e8edf6; }}
  h1 {{ font-size: 44px; font-weight: 800; letter-spacing: -0.015em; margin-top: 6px; text-shadow: 0 2px 18px rgba(0,0,0,0.45); }}
  .sub {{ margin-top: 8px; font-size: 16px; color: #b6c1d4; max-width: 900px; line-height: 1.45; text-shadow: 0 1px 10px rgba(0,0,0,0.5); }}
  .sub b {{ color: #e8edf6; font-weight: 600; }}
  .heroNums {{ display: flex; gap: 12px; flex-shrink: 0; }}
  .hero {{ min-width: 150px; padding: 13px 16px 11px; text-align: center; }}
  .hero .v {{ font-size: 25px; font-weight: 800; font-variant-numeric: tabular-nums; }}
  .hero .v.wc {{ color: #7fd6ff; }}
  .hero .v.cc {{ color: #ff9a6b; }}
  .hero .k {{ margin-top: 2px; font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #9fb6e2; }}

  .main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 18px; flex: 1; min-height: 0; }}
  .panel {{ padding: 16px 18px; display: flex; flex-direction: column; }}
  .ptitle {{ display: flex; align-items: baseline; gap: 9px; }}
  .ptitle .t {{ font-size: 20px; font-weight: 800; letter-spacing: -0.01em; }}
  .ptitle .n {{ font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #7f92b0; }}
  .west .t {{ color: #7fd6ff; }}
  .china .t {{ color: #ff9a6b; }}
  .psub {{ margin-top: 3px; font-size: 12.5px; color: #93a3bd; }}

  .cols {{ display: grid; grid-template-columns: 42px 1fr 104px 128px 44px; gap: 11px; align-items: center;
    margin-top: 12px; padding: 0 8px 6px; border-bottom: 1px solid rgba(255,255,255,0.09);
    font-size: 9.5px; font-weight: 800; letter-spacing: 0.11em; text-transform: uppercase; color: #7f92b0; }}
  .cols .c {{ text-align: center; }} .cols .r {{ text-align: right; }}

  .row {{ display: grid; grid-template-columns: 42px 1fr 104px 128px 44px; gap: 11px; align-items: center;
    padding: 7px 8px; border-radius: 10px; }}
  .row:nth-child(odd) {{ background: rgba(255,255,255,0.035); }}
  .ico {{ width: 40px; height: 40px; border-radius: 9px; border: 1px solid rgba(255,255,255,0.18); display: block; }}
  .nm {{ font-size: 16.5px; font-weight: 700; line-height: 1.15; }}
  .ln {{ font-size: 10px; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase; color: #7f92b0; }}

  .ranks {{ display: flex; align-items: baseline; justify-content: center; gap: 6px; font-variant-numeric: tabular-nums; }}
  .ranks .hi {{ font-size: 19px; font-weight: 800; }}
  .ranks .lo {{ font-size: 15px; font-weight: 700; color: #8b93a7; }}
  .ranks .sep {{ font-size: 9px; font-weight: 700; color: #55637d; text-transform: uppercase; }}
  .hi.wc {{ color: #7fd6ff; }} .hi.cc {{ color: #ff9a6b; }}
  .track {{ display: flex; justify-content: center; }}
  .swing {{ text-align: right; font-size: 17px; font-weight: 800; font-variant-numeric: tabular-nums; }}
  .swing.wc {{ color: #7fd6ff; }} .swing.cc {{ color: #ff9a6b; }}

  .foot {{ display: flex; align-items: center; justify-content: space-between; margin-top: 14px; font-size: 12.5px; color: #8798b3; }}
  .foot b {{ color: #4f8dff; font-weight: 800; }}
</style>
</head>
<body>
<div class="slide">
  <div class="bg-art"></div><div class="bg-dark"></div><div class="bg-vignette"></div>

  <div class="head">
    <div>
      <div class="brand">WRTRUE<span>META</span></div>
      <h1>{ordinal(top_w["westRank"])} in EU + NA. {ordinal(top_w["cnRank"])} in China.</h1>
      <p class="sub">Every champion placed against its own peers on each server, then the two placings
        compared. <b>Rank, not win rate</b>: the EU + NA figure is a champion&rsquo;s 50 best players, China&rsquo;s is a
        whole Challenger bracket, and those two scales should never be subtracted from each other.
        Position inside your own population is a question both can answer.</p>
    </div>
    <div class="heroNums">
      <div class="hero glass"><div class="v wc">{top_w['westRank']} to {top_w['cnRank']}</div><div class="k">{top_w['name']}</div></div>
      <div class="hero glass"><div class="v cc">{top_c['cnRank']} to {top_c['westRank']}</div><div class="k">{top_c['name']}</div></div>
    </div>
  </div>

  <div class="main">
    <div class="panel glass west">
      <div class="ptitle"><span class="t">Stronger in EU + NA</span><span class="n">Top 50 per champion</span></div>
      <div class="psub">Near the top on our boards, nowhere near it in China.</div>
      <div class="cols"><div></div><div>Champion</div><div class="c">EU+NA vs CN</div><div class="c">Placing</div><div class="r">Swing</div></div>
      {side(west_side, total, "#7fd6ff", "wc", True)}
    </div>

    <div class="panel glass china">
      <div class="ptitle"><span class="t">Stronger in China</span><span class="n">Challenger bracket</span></div>
      <div class="psub">Top of the board there, ignored on ours.</div>
      <div class="cols"><div></div><div>Champion</div><div class="c">CN vs EU+NA</div><div class="c">Placing</div><div class="r">Swing</div></div>
      {side(china_side, total, "#ff9a6b", "cc", False)}
    </div>
  </div>

  <div class="foot">
    <div>{total} champions ranked on both. EU + NA is the average of our two top-50 boards
      ({meta['euDate']} and {meta['naDate']}); China is the official Challenger sample ({meta['cnDate']}).</div>
    <div><b>wrtruemeta.com</b></div>
  </div>
</div>
</body>
</html>
"""


def main() -> None:
    html = build()
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
