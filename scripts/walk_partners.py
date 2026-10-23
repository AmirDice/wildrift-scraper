"""Capture the CN companion app's best-partner (duo) lists.

The hero list's 最佳搭档 view ranks two-champion pairs: pick YOUR lane in the
left sidebar, the PARTNER's lane from the chips beside 搭档, and every row is
(champion, partner, win rate, appearance rate). Five lanes times four partner
lanes is 20 lists, all on one page, with no champion page to open.

Everything is read from the UI hierarchy, not pixels. The app is React
Native, so names and percentages are real TextViews, and Android reports a
whole list in one dump, scrolled-out rows included. The walker still scrolls
and merges, keyed by (champion, partner), in case a list loads lazily.

Each list's raw nodes are saved beside the parsed rows, so a parsing fix can
be re-run with --reparse without touching the phone.

Before running: open 英雄榜, switch to 最佳搭档, and set the rank filter at
the top right (峡谷之巅 for Legendary). The filter persists across lanes.

Run:
    python -m scripts.walk_partners --probe          # what the device reports
    python -m scripts.walk_partners --bracket legendary
    python -m scripts.walk_partners --reparse data/captures_partners/<stamp>
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adb_client import ADBClient, ADBError
from src import uiauto
from src.ocr import cn_champion_names, match_cn_name

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "captures_partners"

LANES = [("上单", "baron"), ("打野", "jungle"), ("中单", "mid"), ("下路", "dragon"), ("辅助", "support")]
LANE_CN = {cn for cn, _en in LANES}
LANE_EN = dict(LANES)

#: The page: its tab title, and the label the partner chips sit beside.
SIG_PAGE = ("最佳搭档",)
PARTNER_LABEL = "搭档"
#: Column headers, used to tell the win-rate column from appearance.
HEAD_WR = ("胜率",)
HEAD_PICK = ("出场", "登场")

PERCENT = re.compile(r"^\s*(\d{1,3}(?:\.\d+)?)\s*%\s*$")
#: The sidebar is the left strip of the screen.
SIDEBAR_MAX_X = 0.2
DRY_SCROLLS = 2


def _nodes_json(nodes) -> list[dict]:
    return [{"text": n.text, "desc": n.desc, "bounds": list(n.bounds)} for n in nodes]


def _from_json(raw: list[dict]):
    return [uiauto.Node(text=r["text"], desc=r["desc"], cls="", clickable=False, bounds=tuple(r["bounds"])) for r in raw]


def sidebar(nodes, width):
    """Your-lane options: lane labels in the left strip, top to bottom."""
    return [n for n in uiauto.find_all(nodes, LANE_CN) if n.center[0] < width * SIDEBAR_MAX_X]


def chips(nodes, width):
    """Partner-lane chips: lane labels on the 搭档 row, right of it."""
    anchor = uiauto.find(nodes, PARTNER_LABEL, exact=True)
    if anchor is None:
        return []
    tol = max(24, anchor.bounds[3] - anchor.bounds[1])
    return [n for n in uiauto.find_all(nodes, LANE_CN)
            if abs(n.center[1] - anchor.center[1]) <= tol and n.center[0] > anchor.center[0]]


def parse_rows(nodes, width, names: dict[str, str]) -> list[dict]:
    """Every pair row: two champions, each with the lane printed under its
    name, plus win rate and appearance rate.

    The order inside a row is NOT yours-then-partner: with 打野 picked on the
    left and 上单 on the chips, and the other way round, the app shows the
    same list with the 上单 champion on top. So each champion's lane is read
    from the label under its name, never inferred from position.

    A row is anchored on its two percentages, which share a line; the
    champions are the name nodes in that row's band, top to bottom. The
    band is half the median row pitch either side, measured from this very
    dump, so it holds on any screen size.
    """
    pct = [(n, float(PERCENT.match(n.label).group(1))) for n in nodes
           if n.label and PERCENT.match(n.label) and n.center[0] > width * SIDEBAR_MAX_X]
    pct.sort(key=lambda p: (p[0].center[1], p[0].center[0]))
    lines: list[list] = []
    for node, value in pct:
        tol = max(20, (node.bounds[3] - node.bounds[1]) // 2)
        if lines and abs(lines[-1][0][0].center[1] - node.center[1]) <= tol:
            lines[-1].append((node, value))
        else:
            lines.append([(node, value)])
    lines = [sorted(line, key=lambda p: p[0].center[0]) for line in lines if len(line) >= 2]
    if not lines:
        return []
    ys = [line[0][0].center[1] for line in lines]
    pitch = statistics.median([b - a for a, b in zip(ys, ys[1:])]) if len(ys) > 1 else 200

    # Which column is which, from the headers when present; else the app's
    # order on screen, win rate first.
    head_wr = uiauto.find(nodes, *HEAD_WR)
    head_pick = uiauto.find(nodes, *HEAD_PICK)
    wr_first = True
    if head_wr and head_pick:
        wr_first = head_wr.center[0] < head_pick.center[0]

    named = []
    lane_labels = []
    for n in nodes:
        label = (n.label or "").strip()
        if not label or PERCENT.match(label) or label.isdigit():
            continue
        if label in LANE_CN:
            if n.center[0] > width * SIDEBAR_MAX_X:
                lane_labels.append(n)
            continue
        champion = names.get(label) or match_cn_name(label, names)
        if champion:
            named.append((n, champion, label))

    def lane_under(name_node):
        """The lane label just below a champion's name, inside its row."""
        x0 = name_node.bounds[0]
        below = [n for n in lane_labels
                 if 0 < n.center[1] - name_node.center[1] <= pitch / 3 and abs(n.bounds[0] - x0) <= 60]
        return LANE_EN.get(min(below, key=lambda n: n.center[1]).label.strip()) if below else None

    rows = []
    for line, y in zip(lines, ys):
        band = [(n, c, raw) for n, c, raw in named if abs(n.center[1] - y) <= pitch / 2]
        band.sort(key=lambda t: t[0].center[1])
        if len(band) < 2:
            continue
        a, b = band[0], band[-1]
        first, second = line[0][1], line[1][1]
        rows.append({
            "a": a[1], "aLane": lane_under(a[0]), "b": b[1], "bLane": lane_under(b[0]),
            "cn": [a[2], b[2]],
            "winRate": first if wr_first else second,
            "pickRate": second if wr_first else first,
        })
    return rows


def capture_list(client, width, height, names) -> tuple[list[dict], list[list[dict]]]:
    """Rows of the list now on screen, scrolling until nothing new appears."""
    seen: dict[tuple[str, str], dict] = {}
    raw_dumps = []
    dry = 0
    while dry < DRY_SCROLLS:
        nodes = uiauto.dump(client)
        raw_dumps.append(_nodes_json(nodes))
        new = 0
        for row in parse_rows(nodes, width, names):
            key = (row["a"], row["b"])
            if key not in seen:
                seen[key] = row
                new += 1
        if new == 0:
            dry += 1
        else:
            dry = 0
        client.swipe(int(width * 0.6), int(height * 0.8), int(width * 0.6), int(height * 0.3), 400)
        time.sleep(0.8)
    return list(seen.values()), raw_dumps


def _tap(client, node):
    x, y = node.center
    client.tap(x, y)


def walk(client, args) -> int:
    names = cn_champion_names()
    shot = client.screenshot()
    height, width = shot.shape[:2]
    nodes = uiauto.dump(client)
    if not uiauto.on_screen(nodes, *SIG_PAGE):
        print("Not on the 最佳搭档 page. Open 英雄榜, switch to 最佳搭档, set the "
              "rank filter, then run again.", file=sys.stderr)
        return 2
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = args.out / f"partners_{args.bracket}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    result = {"capturedAt": datetime.now().replace(microsecond=0).isoformat(),
              "bracket": args.bracket, "source": "cn-companion-app 最佳搭档", "lists": []}

    own_lanes = [lane for lane in LANES if not args.lanes or lane[1] in args.lanes]
    done: set[frozenset] = set()
    for own_cn, own_en in own_lanes:
        side = next((n for n in sidebar(nodes, width) if n.label.strip() == own_cn), None)
        if side is None:
            print(f"  {own_en}: lane not in the sidebar, skipped")
            continue
        _tap(client, side)
        time.sleep(1.0)
        nodes = uiauto.dump(client)
        partner_chips = [n.label.strip() for n in chips(nodes, width)]
        if not partner_chips:
            print(f"  {own_en}: no partner chips beside {PARTNER_LABEL}, skipped")
            continue
        for partner_cn in partner_chips:
            # Mirrored lists are the same list (打野+上单 shows exactly what
            # 上单+打野 does), so each lane pair is captured once.
            pair = frozenset((own_cn, partner_cn))
            if pair in done:
                continue
            done.add(pair)
            chip = next((n for n in chips(nodes, width) if n.label.strip() == partner_cn), None)
            if chip is None:
                continue
            _tap(client, chip)
            time.sleep(1.0)
            rows, dumps = capture_list(client, width, height, names)
            # Again sorted by appearance, merged: if the app cuts a list
            # short, the default win-rate order would keep only rare pairs
            # that happened to win and drop the ones people actually play.
            head = uiauto.find(uiauto.dump(client), *HEAD_PICK)
            if head is not None:
                _tap(client, head)
                time.sleep(1.0)
                more, more_dumps = capture_list(client, width, height, names)
                known = {(r["a"], r["b"]) for r in rows}
                rows += [r for r in more if (r["a"], r["b"]) not in known]
                dumps += more_dumps
                back = uiauto.find(uiauto.dump(client), *HEAD_WR)
                if back is not None:
                    _tap(client, back)
                    time.sleep(0.8)
            partner_en = LANE_EN.get(partner_cn, partner_cn)
            name = f"{own_en}__{partner_en}"
            (out / f"{name}.nodes.json").write_text(json.dumps(dumps, ensure_ascii=False), encoding="utf-8")
            result["lists"].append({"lane": own_en, "partnerLane": partner_en, "rows": rows})
            print(f"  {own_en} + {partner_en}: {len(rows)} pairs")
            # Back to the top of the list for the next chip.
            for _ in range(3):
                client.swipe(int(width * 0.6), int(height * 0.3), int(width * 0.6), int(height * 0.85), 300)
            time.sleep(0.6)
            nodes = uiauto.dump(client)
    (out / "partners.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(lst["rows"]) for lst in result["lists"])
    print(f"wrote {out.relative_to(ROOT)}: {len(result['lists'])} lists, {total} pairs")
    return 0


def reparse(folder: Path, width: int) -> int:
    names = cn_champion_names()
    data = json.loads((folder / "partners.json").read_text(encoding="utf-8"))
    for lst in data["lists"]:
        path = folder / f"{lst['lane']}__{lst['partnerLane']}.nodes.json"
        if not path.exists():
            continue
        seen: dict[tuple[str, str], dict] = {}
        for raw in json.loads(path.read_text(encoding="utf-8")):
            for row in parse_rows(_from_json(raw), width, names):
                seen.setdefault((row["a"], row["b"]), row)
        lst["rows"] = list(seen.values())
        print(f"  {lst['lane']} + {lst['partnerLane']}: {len(lst['rows'])} pairs")
    (folder / "partners.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def probe(client) -> int:
    nodes = uiauto.dump(client)
    shot = client.screenshot()
    height, width = shot.shape[:2]
    print(f"screen {width}x{height}, {len(nodes)} nodes, page signature: {uiauto.on_screen(nodes, *SIG_PAGE)}")
    print("sidebar:", [n.label for n in sidebar(nodes, width)])
    print("chips:  ", [n.label for n in chips(nodes, width)])
    rows = parse_rows(nodes, width, cn_champion_names())
    print(f"rows parsed: {len(rows)}")
    for row in rows[:6]:
        print("  ", row)
    if not rows:
        print("no rows: the labels below are what the device reports, top to bottom")
        for n in sorted(nodes, key=lambda n: (n.bounds[1], n.bounds[0]))[:80]:
            if n.label.strip():
                print(f"   {n.bounds} {n.label!r}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bracket", default="legendary", help="the rank filter you set on the page (provenance only)")
    ap.add_argument("--lanes", default="", help="comma-separated subset of YOUR lanes, e.g. 'support,dragon'")
    ap.add_argument("--device", default=ADBClient.device)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--probe", action="store_true", help="print what the device reports on this screen and exit")
    ap.add_argument("--reparse", type=Path, default=None, help="re-run row parsing on a saved capture folder")
    ap.add_argument("--width", type=int, default=1080, help="screen width for --reparse (default 1080)")
    args = ap.parse_args()
    args.lanes = {s.strip() for s in args.lanes.split(",") if s.strip()}
    if args.reparse:
        return reparse(args.reparse, args.width)
    client = ADBClient(device=args.device)
    try:
        client.connect()
    except ADBError as exc:
        print(f"adb: {exc}", file=sys.stderr)
        return 2
    return probe(client) if args.probe else walk(client, args)


if __name__ == "__main__":
    raise SystemExit(main())
