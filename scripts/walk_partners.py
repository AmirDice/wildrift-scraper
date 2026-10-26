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
Native, so names and percentages are real TextViews, and the hierarchy holds
all 100 rows of a list at once (off-screen ones with zero size but full
text), so each list is ONE dump read in document order: no scrolling. Each list's raw nodes are saved
beside the parsed rows, so a parsing fix can be re-run without the phone.

Standalone, from the 英雄榜 page:

    python -m scripts.walk_partners --probe          # what the device reports
    python -m scripts.walk_partners --bracket legendary
    python -m scripts.walk_partners --reparse data/captures/partners/<date>/<stamp>
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
#: Kept for importers. Captures go into the day's partners run,
#: data/captures/partners/<date>/ (src/capture_runs.py), earlier days archived.
OUT = ROOT / "data" / "captures" / "partners"

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
    """Every row of the list, read in DOCUMENT order, bounds ignored.

    The hierarchy carries the whole list, all 100 rows: those on screen with
    real bounds, the rest with zero size but their full text. In document
    order each row is: rank, name, lane, name, lane, win rate, appearance.
    So one dump is the whole list, with no scrolling, no rows lost to the
    sticky header and no boundary row skipped between scrolls; all three
    happened when rows were read by position (first device captures,
    2026-10-23).

    Each champion's lane is the label after its name: the order inside a row
    is not yours-then-partner (打野 picked with 上路, and the other way round,
    show the same list with the 上路 champion first).
    """
    seq = [n for n in nodes
           if (n.label or "").strip() and (n.bounds[0] + n.bounds[2]) / 2 > width * SIDEBAR_MAX_X]
    start = 0
    for i, n in enumerate(seq):
        if n.label.strip() == PARTNER_LABEL:
            start = i + 1
    wr_first = True
    head_wr = uiauto.find(nodes, *HEAD_WR)
    head_pick = uiauto.find(nodes, *HEAD_PICK)
    if head_wr and head_pick:
        wr_first = head_wr.center[0] < head_pick.center[0]

    rows, cur = [], None
    for n in seq[start:]:
        label = n.label.strip()
        if "到底" in label:                       # 已经到底啦~, the list's end
            break
        if label.isdigit() and 1 <= int(label) <= LIST_ROWS:
            cur = {"rank": int(label), "champs": [], "lanes": [], "cn": [], "pct": []}
            rows.append(cur)
            continue
        if cur is None:
            continue
        m = PERCENT.match(label)
        if m:
            cur["pct"].append(float(m.group(1)))
        elif label in LANE_EN:
            cur["lanes"].append(LANE_EN[label])
        else:
            champion = names.get(label) or match_cn_name(label, names)
            if champion:
                cur["champs"].append(champion)
                cur["cn"].append(label)
    out = []
    for r in rows:
        # A complete row only; anything else is reported by the caller as a
        # missing rank rather than guessed.
        if len(r["champs"]) != 2 or len(r["lanes"]) != 2 or len(r["pct"]) != 2:
            continue
        first, second = r["pct"]
        out.append({
            "rank": r["rank"],
            "a": r["champs"][0], "aLane": r["lanes"][0],
            "b": r["champs"][1], "bLane": r["lanes"][1],
            "cn": r["cn"],
            "winRate": first if wr_first else second,
            "pickRate": second if wr_first else first,
        })
    return out


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


def _matches(rows: list[dict], lanes: set[str]) -> bool:
    """Is the list on screen the one asked for? Most rows carry its two
    lanes (the app files the odd pair elsewhere, so not all of them)."""
    if not rows:
        return False
    hits = sum(1 for r in rows if {r["aLane"], r["bLane"]} == lanes)
    return hits >= len(rows) * 0.8


def capture_list(client, width, height, names, lanes: set[str], chip=None) -> tuple[list[dict], list[list[dict]]]:
    """The whole list from one dump (see parse_rows), checked to be the list
    for `lanes`.

    Straight after a chip tap the app can still be showing the previous
    list, and a dump taken then would file Baron + Jungle under Baron + Mid.
    So the rows' own lanes are checked against the chip: on a mismatch it
    waits and reads again, then taps the chip again, and gives up on the
    list rather than save the wrong one.
    """
    dumps = []
    for attempt in range(4):
        nodes = uiauto.dump(client)
        dumps.append(_nodes_json(nodes))
        rows = parse_rows(nodes, width, names)
        if _matches(rows, lanes):
            return rows, dumps
        if attempt == 1 and chip is not None:
            print("    the list did not change; tapping the chip again")
            _tap(client, chip)
        time.sleep(1.2)
    return [], dumps


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


def capture_partners(client, bracket: str, bracket_cn: str, out_root: Path | None = None,
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
    if out_root is None:
        from src.capture_runs import run_for_partners
        out_root = run_for_partners()
    out = out_root / f"partners_{bracket}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    result = {"capturedAt": datetime.now().replace(microsecond=0).isoformat(),
              "bracket": bracket, "bracketCn": bracket_cn, "source": "cn-companion-app 最佳拍档", "lists": []}

    done: set[frozenset] = set()
    for own_cn, own_en in [lane for lane in LANES if not lanes or lane[1] in lanes]:
        if own_en == "support" or all(frozenset((own_en, x)) in done for x in LANE_EN.values() if x != own_en):
            # Every pairing with this lane is already in: 辅助's are taken
            # from the other four tabs (Dragon + Support from 下路, ...).
            print(f"  partners: {own_en}: every pairing already captured from the other lanes")
            continue
        side = next((n for n in sidebar(nodes, width) if LANE_EN.get(n.label.strip()) == own_en), None)
        if side is None:
            print(f"  partners: {own_en} not in the sidebar, skipped")
            continue
        print(f"  partners: opening {side.label.strip()} ({own_en})")
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
                print(f"  partners: no {partner_cn} chip, skipped")
                continue
            print(f"  partners: {own_en} + {partner_en}: tapping {partner_cn}")
            _tap(client, chip)
            time.sleep(1.0)
            # One read: the hierarchy holds all 100 rows, so there is nothing
            # to scroll, and the app's two sorts (胜率, 登场) list the same 100
            # pairs, so the walk does not touch them.
            rows, dumps = capture_list(client, width, height, names, {own_en, partner_en}, chip)
            if not rows:
                print(f"  partners: {own_en} + {partner_en}: the screen never showed this list, skipped")
                continue
            (out / f"{own_en}__{partner_en}.nodes.json").write_text(
                json.dumps({"winRate": dumps}, ensure_ascii=False), encoding="utf-8")
            result["lists"].append({"lane": own_en, "partnerLane": partner_en, "rows": rows})
            # Saved after every list, so a run stopped part-way keeps them.
            (out / "partners.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
            missing = sorted(set(range(1, LIST_ROWS + 1)) - {r["rank"] for r in rows if r.get("rank")})
            print(f"  partners: {own_en} + {partner_en}: {len(rows)} pairs"
                  + (f" (ranks not read by win rate: {len(missing)})" if missing and len(rows) < LIST_ROWS else ""))
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
    ap.add_argument("--out", type=Path, default=None,
                    help="default: today's partners run, data/captures/partners/<date>/")
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
