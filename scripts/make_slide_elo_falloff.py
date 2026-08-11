"""
Build the "scales with elo / falls off up top" slide.

This is the /ranks page as a single shareable image: the same two groups, the
same definition of change, the same cumulative brackets. If the slide and the
page ever disagree, the slide is wrong.

    python scripts/make_slide_elo_falloff.py

Writes web-next/public/elo_falloff_2026.html at 1600x1000, matching the house
style of universal_picks_2026.html.

METHOD, kept deliberately identical to web-next/src/lib/skew.ts:

  * change = Challenger win rate minus Diamond+ win rate, rounded to one place.
  * "Scales with elo" is change >= +1.5, "Falls off up top" is change <= -1.5.
  * A champion needs all three ranked brackets and must hold the SAME lane in
    all of them, so a lane switch cannot masquerade as a skill curve.

  CN Legendary is excluded. It is a separate solo queue rather than the next
  rung above Challenger, and /ranks already presents it that way.

  No field centring here, unlike the win rates themselves. The whole-field
  drift from Diamond+ to Challenger is +0.03, small enough to ignore, and
  matching the published page matters more than removing it.

  Both lists are shown COMPLETE, not topped up or trimmed to a round number.
  Twelve champions clear each threshold and twelve appear on each side, so the
  slide cannot be accused of picking the flattering ones.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CN = ROOT / "web-next" / "src" / "data" / "cn.json"
OUT = ROOT / "web-next" / "public" / "elo_falloff_2026.html"

ICON = "https://game.gtimg.cn/images/lgamem/act/lrlib/img/HeadIcon/H_S_{hero}.png"

CLIMB_AT = 1.5
STOMP_AT = -1.5


def load_rows() -> list[dict]:
    data = json.loads(CN.read_text(encoding="utf-8"))
    rows = []
    for c in data["champions"]:
        bb = c["byBracket"]
        if not all(k in bb for k in ("1", "2", "3")):
            continue
        if len({bb[k]["position"] for k in ("1", "2", "3")}) > 1:
            continue
        d, m, ch = bb["1"], bb["2"], bb["3"]
        rows.append({
            "name": c["name"], "hero": c["heroId"], "lane": d["position"],
            "d": d["winRate"], "m": m["winRate"], "c": ch["winRate"],
            # round1() exactly as lib/skew.ts does it, so the slide and the
            # page never disagree on a boundary case.
            "skew": round((ch["winRate"] - d["winRate"]) * 10) / 10,
        })
    return rows


def spark(row: dict, lo: float, hi: float, colour: str) -> str:
    """Diamond+ / Master+ / Challenger, on a scale shared across the slide."""
    w, h, pad = 92, 34, 6
    span = max(hi - lo, 0.1)
    xs = [pad, w / 2, w - pad]
    ys = [h - pad - (v - lo) / span * (h - 2 * pad) for v in (row["d"], row["m"], row["c"])]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" aria-hidden="true">'
        f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>'
        f'<circle cx="{xs[0]:.1f}" cy="{ys[0]:.1f}" r="2.6" fill="#7f92b0"/>'
        f'<circle cx="{xs[2]:.1f}" cy="{ys[2]:.1f}" r="3.2" fill="{colour}"/>'
        f"</svg>"
    )


def side(rows: list[dict], lo: float, hi: float, colour: str, cls: str) -> str:
    out = []
    for r in rows:
        out.append(f"""
        <div class="row">
          <img class="ico" src="{ICON.format(hero=r['hero'])}" alt="">
          <div><div class="nm">{r['name']}</div><div class="ln">{r['lane']}</div></div>
          <div class="sp">{spark(r, lo, hi, colour)}</div>
          <div class="wrs"><span class="a">{r['d']:.1f}</span><span class="t">to</span><span class="b {cls}">{r['c']:.1f}</span></div>
          <div class="chg {cls}">{r['skew']:+.1f}</div>
        </div>""")
    return "".join(out)


def build() -> str:
    rows = load_rows()
    climb = sorted([r for r in rows if r["skew"] >= CLIMB_AT], key=lambda r: -r["skew"])
    stomp = sorted([r for r in rows if r["skew"] <= STOMP_AT], key=lambda r: r["skew"])

    both = climb + stomp
    lo = min(min(r["d"], r["m"], r["c"]) for r in both)
    hi = max(max(r["d"], r["m"], r["c"]) for r in both)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex,nofollow">
<title>Scales With Elo, Falls Off Up Top | WrTrueMeta</title>
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
  /* The site's own backdrop, copied verbatim from app/layout.tsx: the same art,
     the same three layers, the same opacities. A slide that is meant to look
     like the site has to use the site's background, not one that merely
     resembles it. */
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

  .head {{ display: flex; align-items: flex-end; justify-content: space-between; }}
  .brand {{ font-size: 20px; font-weight: 800; letter-spacing: 0.16em; text-transform: uppercase; color: #4f8dff; }}
  .brand span {{ color: #e8edf6; }}
  h1 {{ font-size: 43px; font-weight: 800; letter-spacing: -0.015em; margin-top: 6px; text-shadow: 0 2px 18px rgba(0,0,0,0.45); }}
  .sub {{ margin-top: 8px; font-size: 16px; color: #b6c1d4; max-width: 900px; line-height: 1.45; text-shadow: 0 1px 10px rgba(0,0,0,0.5); }}
  .sub b {{ color: #e8edf6; font-weight: 600; }}
  .legend {{ text-align: right; font-size: 12.5px; color: #9fb6e2; line-height: 1.7; }}
  .legend b {{ color: #e8edf6; }}

  .main {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 18px; flex: 1; min-height: 0; }}
  .panel {{ padding: 16px 18px; display: flex; flex-direction: column; }}
  .ptitle {{ display: flex; align-items: baseline; gap: 9px; }}
  .ptitle .t {{ font-size: 19px; font-weight: 800; letter-spacing: -0.01em; }}
  .ptitle .n {{ font-size: 11px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: #7f92b0; }}
  .psub {{ margin-top: 3px; font-size: 12.5px; color: #93a3bd; }}
  .up .t {{ color: #6ee7a8; }}
  .dn .t {{ color: #ff7a6b; }}

  .cols {{ display: grid; grid-template-columns: 40px 1fr 92px 104px 52px; gap: 11px; align-items: center;
    margin-top: 11px; padding: 0 8px 6px; border-bottom: 1px solid rgba(255,255,255,0.09);
    font-size: 9.5px; font-weight: 800; letter-spacing: 0.11em; text-transform: uppercase; color: #7f92b0; }}
  .cols .c {{ text-align: center; }} .cols .r {{ text-align: right; }}

  .row {{ display: grid; grid-template-columns: 40px 1fr 92px 104px 52px; gap: 11px; align-items: center;
    padding: 6px 8px; border-radius: 10px; }}
  .row:nth-child(odd) {{ background: rgba(255,255,255,0.035); }}
  .ico {{ width: 38px; height: 38px; border-radius: 9px; border: 1px solid rgba(255,255,255,0.18); display: block; }}
  .nm {{ font-size: 16px; font-weight: 700; line-height: 1.15; }}
  .ln {{ font-size: 10px; font-weight: 700; letter-spacing: 0.09em; text-transform: uppercase; color: #7f92b0; }}
  .sp {{ display: flex; justify-content: center; }}

  .wrs {{ display: flex; align-items: center; justify-content: center; gap: 5px; font-variant-numeric: tabular-nums; }}
  .wrs .a {{ font-size: 13.5px; font-weight: 650; color: #93a3bd; }}
  .wrs .t {{ font-size: 9px; font-weight: 700; color: #55637d; text-transform: uppercase; }}
  .wrs .b {{ font-size: 14.5px; font-weight: 750; }}
  .chg {{ text-align: right; font-size: 16px; font-weight: 800; font-variant-numeric: tabular-nums; }}
  .gain {{ color: #6ee7a8; }} .loss {{ color: #ff7a6b; }}

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
      <h1>Who Gets Better When The Lobby Does</h1>
      <p class="sub">Every champion that moves at least <b>1.5 win rate points</b> between Diamond+ and
        Challenger, in both directions. These are cumulative samples, so Diamond+ already contains the
        players above it: this is the same champion measured in a pool, then inside the best slice of it.</p>
    </div>
    <div class="legend">
      Sparkline runs<br><b>Diamond+ to Master+ to Challenger</b><br>
      Change is Challenger minus Diamond+
    </div>
  </div>

  <div class="main">
    <div class="panel glass">
      <div class="ptitle up"><span class="t">Scales with elo</span><span class="n">{len(climb)} champions</span></div>
      <div class="psub">Better in stronger company. Reward for knowing the champion.</div>
      <div class="cols"><div></div><div>Champion</div><div class="c">Curve</div><div class="c">D+ to Chal</div><div class="r">Chg</div></div>
      {side(climb, lo, hi, "#6ee7a8", "gain")}
    </div>

    <div class="panel glass">
      <div class="ptitle dn"><span class="t">Falls off up top</span><span class="n">{len(stomp)} champions</span></div>
      <div class="psub">Strong to climb with, then the answers get found.</div>
      <div class="cols"><div></div><div>Champion</div><div class="c">Curve</div><div class="c">D+ to Chal</div><div class="r">Chg</div></div>
      {side(stomp, lo, hi, "#ff7a6b", "loss")}
    </div>
  </div>

  <div class="foot">
    <div>China server, official published rates, {len(rows)} champions holding one lane across all three brackets</div>
    <div><b>wrtruemeta.com/ranks</b></div>
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
