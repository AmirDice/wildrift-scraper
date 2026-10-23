"""Capture the CN companion app's best-partner (duo) lists.

The hero list's 最佳拍档 view ranks two-champion pairs: pick a lane in the
left sidebar, the other lane from the chips beside 搭档, and every row is two
champions with the lane printed under each name, the pair's win rate (胜率)
and appearance rate (登场). Mirrored pairs are the same list, so 10 lists
cover every lane pairing, all on one page, with no champion page to open.

Normally run as part of the loadout walk, which captures these first (under
a minute) and then walks the champions:

    python -m scripts.walk_loadouts --bracket legendary --mode classic-ranked --partners

The rank is set from the filter at the top right (钻石以上 and so on), from
the same --bracket as the loadouts.

Everything is read from the UI hierarchy, not pixels. The app is React
Native, so names and percentages are real TextViews, and Android reports a
whole list in one dump, scrolled-out rows included. The walker still scrolls
and merges in case a list loads lazily. Each list's raw nodes are saved
beside the parsed rows, so a parsing fix can be re-run without the phone.

Standalone, from the 英雄榜 page:

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

#: This page writes 上路 and 中路; the champion pages say 上单 and 中单.
#: Both are accepted wherever a lane label is read.
LANES = [("上路", "baron"), ("打野", "jungle"), ("中路", "mid"), ("下路", "dragon"), ("辅助", "support")]
LANE_EN = {**dict(LANES), "上单": "baron", "中单": "mid"}
LANE_CN = set(LANE_EN)

#: The view's tab beside 英雄榜, and the label the partner chips sit beside.
PAGE_TAB = "最佳拍档"
HERO_LIST_TAB = "英雄榜"
SIG_PAGE = ("搭档",)
PARTNER_LABEL = "搭档"
#: Column headers, used to tell the win-rate column from appearance.
HEAD_WR = ("胜率",)
HEAD_PICK = ("登场", "出场")
#: The rank filter's options, and the sheet it opens.
RANKS = ("钻石以上", "大师以上", "王者以上", "峡谷之巅")
RANK_SHEET = "段位选择"
CONFIRM = "确定"

#: Every list holds the top 100 pairs. The walk stops once ranks 1..100 are
#: all read, instead of waiting for scrolls that reveal nothing.
LIST_ROWS = 100

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
    left and 上路 on the chips, and the other way round, the app shows the
    same list with the 上路 champion on top. So each champion's lane is read
    from the label under its name, never inferred from position.

    A row is anchored on its two percentages, which share a line; the
    champions are the name nodes in that row's band, top to bottom. The
    band is half the median row pitch either side, measured from this very
    dump, so it holds on any screen size.
    """
    # Only nodes really on screen, below the sticky header. Measured on the
    # first device capture: 644 of 731 labelled nodes had ZERO size, every
    # off-screen row squashed onto one line at the bottom of the list, and
    # parsed as rows they produced pairs like Fiora + Darius at "61.58%"
    # appearance. And a row scrolling under the header keeps its bottom half
    # (赵信 with no partner above it), so nothing above the 搭档 chip row is
    # read at all.
    nodes = [n for n in nodes if n.bounds[2] > n.bounds[0] and n.bounds[3] > n.bounds[1]]
    anchor = uiauto.find(nodes, PARTNER_LABEL, exact=True)
    top = anchor.bounds[3] if anchor is not None else 0
    nodes = [n for n in nodes if n.bounds[1] >= top]
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

    numbers = [n for n in nodes
               if (n.label or "").strip().isdigit() and n.center[0] > width * SIDEBAR_MAX_X
               and 1 <= int(n.label.strip()) <= LIST_ROWS]
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
        # A complete row only: exactly two champions, one above the
        # percentages and one below, each with its lane label. Anything else
        # is a row cut by the header or the bottom of the list, and the next
        # scroll reads it whole.
        if len(band) != 2:
            continue
        a, b = band
        if not (a[0].center[1] < y < b[0].center[1]):
            continue
        if lane_under(a[0]) is None or lane_under(b[0]) is None:
            continue
        first, second = line[0][1], line[1][1]
        rank = next((int(n.label.strip()) for n in numbers if abs(n.center[1] - y) <= pitch / 2), None)
        rows.append({
            "rank": rank,
            "a": a[1], "aLane": lane_under(a[0]), "b": b[1], "bLane": lane_under(b[0]),
            "cn": [a[2], b[2]],
            "winRate": first if wr_first else second,
            "pickRate": second if wr_first else first,
        })
    return rows


def in_order(rows: list[dict], field: str) -> list[dict]:
    """Keep the rows consistent with the list's sort, by rank.

    The app repeats earlier rows at the end of a list: on the first device
    capture rank 98 showed Aatrox + Jarvan IV with rank 26's numbers, 99
    repeated rank 60 and 100 rank 29, right above its own 已经到底啦~. A list
    sorted by `field` never rises down the ranks, so the rows kept are the
    LARGEST set that does not: a longest non-increasing run by rank. A rule
    that compared each row to everything after it let one repeat at rank 100
    throw out every genuine row from 28 to 96. A pair read at two ranks then
    keeps its first.
    """
    ranked = sorted((r for r in rows if r.get("rank")), key=lambda r: (r["rank"], -r[field]))
    n = len(ranked)
    best = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if ranked[j]["rank"] < ranked[i]["rank"] and ranked[j][field] + 0.005 >= ranked[i][field] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    if not n:
        return []
    i = max(range(n), key=lambda k: best[k])
    chain = []
    while i != -1:
        chain.append(ranked[i])
        i = prev[i]
    chain.reverse()
    seen, out = set(), []
    for row in chain:
        key = (row["a"], row["b"])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out


def merge_sorts(by_wr: list[dict], by_pick: list[dict]) -> list[dict]:
    """One row per pair from the two sorts. The sorts number their rows
    separately, so a pair keeps its win-rate rank as `rank` and its
    appearance rank as `pickRank`."""
    rows = {(r["a"], r["b"]): dict(r) for r in by_wr}
    for r in by_pick:
        key = (r["a"], r["b"])
        if key in rows:
            rows[key]["pickRank"] = r.get("rank")
        else:
            rows[key] = {**r, "rank": None, "pickRank": r.get("rank")}
    return list(rows.values())


def rows_from_dumps(dumps: list[list[dict]], width: int, names: dict[str, str], field: str) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for raw in dumps:
        for row in parse_rows(_from_json(raw), width, names):
            seen.setdefault((row["a"], row["b"], row.get("rank")), row)
    return in_order(list(seen.values()), field)


def capture_list(client, width, height, names) -> tuple[list[dict], list[list[dict]]]:
    """All rows of the list on screen: until ranks 1..100 are read, or
    scrolling stops revealing new pairs (a list shorter than 100).

    The hierarchy often holds the whole list at once, which makes this one
    dump; if the app renders rows lazily, it scrolls about a screen at a time
    and merges, keyed by the pair.
    """
    seen: dict[tuple[str, str], dict] = {}
    raw_dumps = []
    dry = 0
    while dry < DRY_SCROLLS:
        ranks = {r["rank"] for r in seen.values() if r.get("rank")}
        if len(ranks) >= LIST_ROWS:
            break
        nodes = uiauto.dump(client)
        raw_dumps.append(_nodes_json(nodes))
        new = 0
        for row in parse_rows(nodes, width, names):
            key = (row["a"], row["b"], row.get("rank"))
            if key not in seen:
                seen[key] = row
                new += 1
        if new == 0:
            dry += 1
        else:
            dry = 0
        # Slow and short: a fast swipe flings past a screen, and on the first
        # capture skipped the boundary row every time (ranks 7-8, 15-16, ...).
        # Half a screen at 1.2s keeps consecutive views overlapping.
        client.swipe(int(width * 0.6), int(height * 0.75), int(width * 0.6), int(height * 0.25), 1200)
        time.sleep(0.6)
    return list(seen.values()), raw_dumps


def _tap(client, node):
    x, y = node.center
    client.tap(x, y)


def _wait(client, *sig, timeout: float = 8.0):
    deadline = time.time() + timeout
    while True:
        nodes = uiauto.dump(client)
        if nodes and uiauto.on_screen(nodes, *sig):
            return nodes
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def open_page(client):
    """From 英雄榜, switch to the 最佳拍档 view. Returns its nodes or None."""
    nodes = uiauto.dump(client)
    if uiauto.find(nodes, PARTNER_LABEL, exact=True) is not None:
        return nodes
    tab = uiauto.find(nodes, PAGE_TAB, exact=True)
    if tab is not None:
        _tap(client, tab)
    else:
        # If "英雄榜 | 最佳拍档" is one text node, tap its right-hand part.
        joined = uiauto.find(nodes, PAGE_TAB)
        if joined is None:
            return None
        x0, y0, x1, y1 = joined.bounds
        client.tap(x1 - (x1 - x0) // 4, (y0 + y1) // 2)
    return _wait(client, PARTNER_LABEL, timeout=10.0)


def _rank_filter(nodes, width, height):
    """The filter at the top right: a rank label in that corner. It shows
    the CURRENT rank, which is how it is told apart from the sheet's options
    in the bottom half when both are on screen."""
    return next((n for n in uiauto.find_all(nodes, set(RANKS))
                 if n.center[1] < height * 0.3 and n.center[0] > width * 0.55), None)


def set_rank(client, nodes, target_cn: str, width: int, height: int):
    """Set the rank filter (钻石以上 and so on) to target, and confirm it."""
    current = _rank_filter(nodes, width, height)
    if current is None:
        print("  partners: rank filter not found at the top right")
        return None
    if current.label.strip() == target_cn:
        return nodes
    _tap(client, current)
    sheet = _wait(client, RANK_SHEET, timeout=6.0)
    if sheet is None:
        print("  partners: the rank sheet did not open")
        return None
    option = next((n for n in uiauto.find_all(sheet, {target_cn}) if n.center[1] > height * 0.5), None)
    if option is None:
        print(f"  partners: {target_cn} not in the rank sheet")
        return None
    _tap(client, option)
    time.sleep(0.4)
    ok = uiauto.find(uiauto.dump(client), CONFIRM, exact=True)
    if ok is not None:
        _tap(client, ok)
    nodes = _wait(client, PARTNER_LABEL, timeout=8.0)
    check = _rank_filter(nodes or [], width, height)
    if check is None or check.label.strip() != target_cn:
        print(f"  partners: the filter reads {check.label if check else 'nothing'}, not {target_cn}")
        return None
    return nodes


def capture_partners(client, bracket: str, bracket_cn: str, out_root: Path = OUT,
                     lanes: set[str] | None = None) -> Path | None:
    """Capture every lane pairing, starting and ending on 英雄榜.

    Called by scripts.walk_loadouts --partners before the champion walk, or
    by this module's CLI. Returns the capture folder, or None.
    """
    names = cn_champion_names()
    height, width = client.screenshot().shape[:2]
    nodes = open_page(client)
    if nodes is None:
        print("  partners: could not open 最佳拍档 from 英雄榜")
        return None
    nodes = set_rank(client, nodes, bracket_cn, width, height)
    if nodes is None:
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out = out_root / f"partners_{bracket}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    result = {"capturedAt": datetime.now().replace(microsecond=0).isoformat(),
              "bracket": bracket, "bracketCn": bracket_cn, "source": "cn-companion-app 最佳拍档", "lists": []}

    done: set[frozenset] = set()
    for own_cn, own_en in [lane for lane in LANES if not lanes or lane[1] in lanes]:
        side = next((n for n in sidebar(nodes, width) if LANE_EN.get(n.label.strip()) == own_en), None)
        if side is None:
            print(f"  partners: {own_en} not in the sidebar, skipped")
            continue
        _tap(client, side)
        time.sleep(1.0)
        nodes = uiauto.dump(client)
        for partner_cn in [n.label.strip() for n in chips(nodes, width)]:
            partner_en = LANE_EN.get(partner_cn, partner_cn)
            # Mirrored lists are the same list (打野 + 上路 shows exactly what
            # 上路 + 打野 does), so each lane pair is captured once.
            pair = frozenset((own_en, partner_en))
            if pair in done:
                continue
            done.add(pair)
            chip = next((n for n in chips(nodes, width) if n.label.strip() == partner_cn), None)
            if chip is None:
                continue
            _tap(client, chip)
            time.sleep(1.0)
            rows, dumps = capture_list(client, width, height, names)
            rows = in_order(rows, "winRate")
            more, more_dumps = [], []
            # Again sorted by appearance: if the app cuts a list short, the
            # default win-rate order keeps only rare pairs that happened to
            # win and drops the ones people actually play.
            head = uiauto.find(uiauto.dump(client), *HEAD_PICK)
            if head is not None:
                _tap(client, head)
                time.sleep(1.0)
                more, more_dumps = capture_list(client, width, height, names)
                more = in_order(more, "pickRate")
                back = uiauto.find(uiauto.dump(client), *HEAD_WR)
                if back is not None:
                    _tap(client, back)
                    time.sleep(0.8)
            rows = merge_sorts(rows, more)
            (out / f"{own_en}__{partner_en}.nodes.json").write_text(
                json.dumps({"winRate": dumps, "pickRate": more_dumps}, ensure_ascii=False), encoding="utf-8")
            result["lists"].append({"lane": own_en, "partnerLane": partner_en, "rows": rows})
            missing = sorted(set(range(1, LIST_ROWS + 1)) - {r["rank"] for r in rows if r.get("rank")})
            print(f"  partners: {own_en} + {partner_en}: {len(rows)} pairs"
                  + (f" (ranks not read by win rate: {len(missing)})" if missing and len(rows) < LIST_ROWS else ""))
            for _ in range(3):
                client.swipe(int(width * 0.6), int(height * 0.3), int(width * 0.6), int(height * 0.85), 300)
            time.sleep(0.6)
            nodes = uiauto.dump(client)
    (out / "partners.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    total = sum(len(lst["rows"]) for lst in result["lists"])
    print(f"  partners: wrote {out.relative_to(ROOT)}: {len(result['lists'])} lists, {total} pairs")
    # Back to the hero list, where the loadout walk starts.
    back = uiauto.find(uiauto.dump(client), HERO_LIST_TAB, exact=True)
    if back is not None:
        _tap(client, back)
        time.sleep(1.0)
    return out


def reparse(folder: Path, width: int) -> int:
    """Rebuild partners.json from the saved nodes alone, so a parsing fix
    needs no phone, and a run stopped part-way still yields its lists."""
    names = cn_champion_names()
    path = folder / "partners.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "capturedAt": None, "bracket": folder.name.split("_")[1] if "_" in folder.name else None,
        "source": "cn-companion-app 最佳拍档"}
    lists = []
    for nodes_file in sorted(folder.glob("*__*.nodes.json")):
        lane, partner_lane = nodes_file.name.removesuffix(".nodes.json").split("__")
        raw = json.loads(nodes_file.read_text(encoding="utf-8"))
        # The first captures saved one list of dumps, win-rate order only.
        by_wr = raw["winRate"] if isinstance(raw, dict) else raw
        by_pick = raw.get("pickRate", []) if isinstance(raw, dict) else []
        rows = merge_sorts(rows_from_dumps(by_wr, width, names, "winRate"),
                           rows_from_dumps(by_pick, width, names, "pickRate"))
        lists.append({"lane": lane, "partnerLane": partner_lane, "rows": rows})
        ranks = {r["rank"] for r in rows if r.get("rank")}
        print(f"  {lane} + {partner_lane}: {len(rows)} pairs, win-rate ranks {len(ranks)}")
    data["lists"] = lists
    if not data.get("capturedAt"):
        stamp = re.search(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})", folder.name)
        if stamp:
            y, mo, d, h, mi = stamp.groups()
            data["capturedAt"] = f"{y}-{mo}-{d}T{h}:{mi}:00"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
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
    if args.probe:
        return probe(client)
    from scripts.walk_loadouts import BRACKET_ALIASES
    bracket_cn = BRACKET_ALIASES.get(args.bracket.strip().lower(), "")
    if not bracket_cn:
        print(f"unknown --bracket {args.bracket!r}", file=sys.stderr)
        return 2
    return 0 if capture_partners(client, args.bracket, bracket_cn, args.out, args.lanes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
