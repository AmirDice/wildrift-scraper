"""Walk the whole roster, capturing every champion's loadout panel.

Drives: hero list -> champion -> 查看更多 -> 国服数据 -> five tabs -> back.
Navigation targets TEXT read off the device (src/uiauto.py), not coordinates,
so an app update that moves a button is a miss we detect rather than a tap
that silently lands somewhere else.

Set the 经典 chip ONCE before starting; it persists across champions. The
LANE and the RANK do not, so both are set per champion, from the two
dropdowns on its page.

EVERY LANE A CHAMPION OFFERS IS CAPTURED, in one visit to its page. The
tables are per lane -- Shen offers 上单 and 打野, Senna 下路 and 辅助 -- and
those are different datasets, not one dataset seen twice. The lane dropdown
is the only place the app says how many a champion has, so it is read there
rather than inferred from which hero-list tabs the champion appears under.

It is RESUMABLE and keyed by (champion, lane), so a run that dies at
champion 90 picks up at 90.

--lanes narrows which hero-list TABS are walked, not what is captured from
the champions found there.

Run:
    python -m scripts.walk_loadouts --bracket challenger --mode classic-ranked
    python -m scripts.walk_loadouts --bracket challenger --mode classic-ranked --lanes baron,jungle
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# The app's labels are Chinese and a Windows console is cp1252, so printing a
# champion name raises UnicodeEncodeError before anything useful happens.
# Reconfigure rather than strip the names: they are what makes the output
# readable against the phone screen sitting next to you.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.adb_client import ADBClient, ADBError
from src import uiauto
from src import loadouts as L
from src.ocr import cn_champion_names
from scripts.scrape_loadouts import capture_champion, DEFAULT_OUT

ROOT = Path(__file__).resolve().parent.parent
CN_WINRATES = ROOT / "data" / "cn_winrates.json"

#: Sidebar lanes, in the order the app lists them.
LANE_ORDER = [("上单", "baron"), ("打野", "jungle"), ("中单", "mid"),
              ("下路", "dragon"), ("辅助", "support")]

#: Text that identifies each screen. Checked before acting, so a failed
#: transition is reported instead of being tapped blindly on top of.
SIG_HERO_LIST = ("英雄榜",)
SIG_CHAMPION = ("查看更多", "国服排行")
SIG_DATA = ("核心装备", "二级鞋")

#: Stop a lane after this many scrolls reveal nobody new.
DRY_SCROLLS = 2

#: Champions the APP cannot show, and why. Not a list of things that are
#: hard: a champion belongs here only once its failure has been reproduced
#: and understood, because every name here is data we are choosing not to
#: collect.
#:
#: Cho'Gath: 查看更多 opens but 国服数据 never finishes loading. Tried twice
#: per lane across two runs at 25s each, and confirmed by hand on the
#: device. Retrying costs 100 seconds a run for nothing.
SKIP_CHAMPIONS = {
    "Cho'Gath": "国服数据 never loads in the app (checked 2026-10-11)",
}

#: Where the skips are written down, beside the captures they are absent
#: from. A champion with no directory is otherwise indistinguishable from
#: one the walk failed on.
NO_DATA_FILE = "_no_data.json"

#: What you may type for --bracket, mapped to the label the app shows.
#: 峡谷之巅 ("top of canyon") is the highest and the default. Note the sample
#: cost: the higher the bracket the fewer games behind each build row, and
#: these tables already show rows resting on single-digit game counts.
BRACKET_ALIASES = {
    "diamond": "钻石以上", "diamond+": "钻石以上",
    "master": "大师以上", "master+": "大师以上",
    "challenger": "王者以上", "king": "王者以上",
    "legendary": "峡谷之巅", "canyon": "峡谷之巅", "top-of-canyon": "峡谷之巅",
}
DEFAULT_BRACKET = "legendary"

#: Tappable band of the hero list, as fractions of height. Above this sit the
#: mode chips and column headers; below it the bottom navigation bar, which
#: would swallow a tap aimed at the last row.
LIST_TOP = 0.22
LIST_BOTTOM = 0.90


def _cn_names() -> dict[str, str]:
    """Chinese champion name -> our English name.

    Shared with the extractor rather than re-read here, because the file on
    its own is not enough: Tencent's hero list has no Hwei at any spelling
    and writes Taliyah as 塔莉垭 where the client shows 塔莉娅. src/ocr.py
    carries those corrections, and a second copy of this map that did not
    have them is exactly how Hwei went uncaptured while every count looked
    almost right.
    """
    return cn_champion_names()


def _wait_for(client, *sig, timeout: float = 8.0):
    """Dump until the screen shows `sig`, or give up. Returns nodes or None.

    Budgeted in SECONDS rather than attempts, because the waits here differ by
    an order of magnitude: a tab switch lands in well under a second, while
    查看更多 takes 7-10s to load its page. A fixed attempt ladder either gives
    up on the slow one or wastes the budget on every fast one.
    """
    deadline = time.time() + timeout
    while True:
        nodes = uiauto.dump(client)           # ~1s, so this paces the poll
        if nodes and uiauto.on_screen(nodes, *sig):
            return nodes
        if time.time() >= deadline:
            return None
        time.sleep(0.5)


def _back_to_list(client, depth: int = 3) -> bool:
    for _ in range(depth):
        client.back()
        if _wait_for(client, *SIG_HERO_LIST, timeout=3.0) is not None:
            return True
    return False


#: How long to wait for a dropdown to open.
#:
#: 5s looked generous for a local menu and was not: the poll IS a hierarchy
#: dump, which costs 2.9s here, so five seconds bought at most two looks.
#: Four lanes were lost to "could not set lane" on champions whose dropdown
#: opens perfectly well by hand -- Dr. Mundo's jungle, and support on Brand,
#: Vel'Koz and Veigar, while the same second-lane selection worked on
#: Morgana, Swain, Galio, Lux and Zyra. Ten seconds is three or four looks
#: and costs nothing in the normal case, because the dropdown opens for
#: every champion, including the one-role ones: not a single run has
#: printed the "did not open" warning.
DIALOG_TIMEOUT = 10.0

#: A HIERARCHY DUMP COSTS 2.9 SECONDS ON THIS DEVICE, and a screenshot 1.7.
#: Measured, not assumed: `uiautomator dump` to a file then `cat` it is
#: 2930ms median, straight to /dev/tty 2743ms, so the round trip is not the
#: cost -- uiautomator itself is. That one number decides the shape of
#: everything below. Every function here TAKES a dump and HANDS ONE BACK
#: instead of fetching its own, because the difference between four dumps
#: per champion and thirteen is an hour across the roster.
#:
#: The sleeps that used to sit before each dump are gone for the same
#: reason: uiauto.dump already retries past "could not get idle state", so
#: the dump IS the wait, and a 0.4s sleep in front of a 2.9s call bought
#: nothing but 0.4s.

#: Where each dropdown's 确定 was last seen. The rank dialog needs one; at
#: the time of writing the lane dialog commits on tap. Rather than hardcode
#: either, the first use of each learns it, and later uses tap the same
#: place blind and confirm from the verification dump that was already
#: being taken. A stale coordinate cannot slip through: the caller checks
#: the chip afterwards, and a miss clears the cache and pays full price.
_CONFIRM_AT: dict[str, tuple[int, int] | None] = {}


def _chips(nodes):
    """(lane chip, rank chip) on a champion page, found as a PAIR.

    The rank chip anchors the search because its labels are unambiguous:
    钻石以上 and friends appear nowhere else on the page. The lane chip is
    then the lane-labelled node on the same row to its left -- which is what
    separates it from 辅助 sitting at (132, 964) as the champion's UTILITY
    RATING, a lane name in every respect except being a lane.
    """
    rank = uiauto.find(nodes, *L.BRACKETS.keys(), exact=True)
    if rank is None:
        return None, None
    # The chip's own height as the row tolerance, so this holds on any
    # device without a second calibration constant to keep in step.
    tol = max(20, rank.bounds[3] - rank.bounds[1])
    row = [n for n in uiauto.find_all(nodes, set(L.LANES))
           if abs(n.center[1] - rank.center[1]) <= tol
           and n.center[0] < rank.center[0]]
    lane = max(row, key=lambda n: n.center[0]) if row else None
    return lane, rank


def _open_dropdown(client, nodes, chip, labels):
    """Tap `chip` open and return (its options, the dump that found them).

    Options are found by DIFFERENCE: the labels on screen after the tap that
    were not there before. Searching for them directly would find the chip
    itself and tap the menu straight back shut.

    No fresh labels means the dropdown never opened, which is how a
    single-option filter presents: there is nothing to choose.
    """
    seen = {n.bounds for n in uiauto.find_all(nodes, labels)}
    client.tap(*chip.center)
    deadline = time.time() + DIALOG_TIMEOUT
    while True:
        latest = uiauto.dump(client)
        fresh = [n for n in uiauto.find_all(latest, labels)
                 if n.bounds not in seen]
        if fresh:
            return fresh, latest
        if time.time() >= deadline:
            return [], latest


def _commit(client, options, target_cn: str, kind: str):
    """Pick `target_cn` out of an OPEN dropdown. Returns the dump after it
    lands, or None when the dropdown does not offer it."""
    match = next((n for n in options if n.label.strip() == target_cn), None)
    if match is None:
        return None
    client.tap(*match.center)

    remembered = _CONFIRM_AT.get(kind)
    if remembered is not None:
        client.tap(*remembered)
        return uiauto.dump(client)

    nodes = uiauto.dump(client)
    if kind in _CONFIRM_AT:          # known to commit on tap
        return nodes
    confirm = uiauto.find(nodes, "确定", exact=True)
    if confirm is None:
        _CONFIRM_AT[kind] = None     # learned: this one needs no confirm
        return nodes
    _CONFIRM_AT[kind] = confirm.center
    client.tap(*confirm.center)
    return uiauto.dump(client)


def _set_filter(client, nodes, target_cn: str, labels, kind: str,
                which: int) -> tuple[bool, list]:
    """Set one of the two chips. Returns (it stuck, the latest dump).

    Verified from the chip afterwards rather than assumed from the tap: a
    missed option leaves the page on its default, and every table captured
    after that would be real data filed under the wrong heading.
    """
    chip = _chips(nodes)[which]
    if chip is None:
        return False, nodes
    if chip.label.strip() == target_cn:
        return True, nodes           # nothing to do, nothing to pay

    options, nodes = _open_dropdown(client, nodes, chip, labels)
    if not options:
        return False, nodes
    after = _commit(client, options, target_cn, kind)
    if after is None:                # not on offer: close and report
        client.back()
        return False, uiauto.dump(client)
    nodes = after

    chip = _chips(nodes)[which]
    if chip is not None and chip.label.strip() == target_cn:
        return True, nodes
    # A remembered 确定 that no longer lands is the one way this goes wrong
    # quietly. Forget it and let the next attempt pay for a fresh look.
    _CONFIRM_AT.pop(kind, None)
    return False, nodes


def set_lane(client, nodes, target_cn: str) -> tuple[bool, list]:
    return _set_filter(client, nodes, target_cn, set(L.LANES), "lane", 0)


def set_rank(client, nodes, target_cn: str) -> tuple[bool, list]:
    """Set the rank filter. This is per champion, not once globally.

    The filter persists between screens but NOT from one champion's page to
    the next, so skipping it silently captures whatever bracket the page
    defaulted to -- and a mixed-bracket dataset is worse than no dataset,
    because nothing about the numbers says which rows came from where.
    """
    return _set_filter(client, nodes, target_cn, set(L.BRACKETS), "rank", 1)


def lanes_for_champion(client, nodes) -> tuple[list[str], list, list, str]:
    """(lanes offered, the still-OPEN options, the latest dump, current lane).

    The fourth value is the label the chip was showing BEFORE the dropdown
    was opened. The caller needs it to close a menu it has no selection to
    make in, and it cannot be read back afterwards: _chips anchors on the
    rank chip, which a dialog covering the page removes from the hierarchy.

    THIS IS THE ROLE COUNT. The loadout tables are per lane: Shen played
    Baron and Shen played Jungle are two different datasets, and so are
    Senna bot and Senna support. Capturing one and labelling it with the
    other's lane does not produce a worse number, it produces a number that
    belongs to a different champion-role.

    The dropdown is the only place the app states this, so it is read per
    champion rather than derived from which hero-list tabs the champion
    appears under -- those two disagree, because a champion can be ranked in
    a lane the loadout panel does not break out.

    The options come back OPEN so the caller can select the first lane it
    wants straight out of them. Closing the menu and reopening it to choose
    would be two more dumps, which is six seconds per champion.
    """
    chip = _chips(nodes)[0]
    if chip is None:
        return [], [], nodes, ""
    current = chip.label.strip()
    options, nodes = _open_dropdown(client, nodes, chip, set(L.LANES))
    if not options:
        # Said out loud, because the quiet version of this is the whole
        # point of the exercise: a dropdown whose options are not exposed as
        # text looks exactly like a champion with one role, and we would
        # capture Shen's Baron table and never know Jungle existed.
        print(f"    ! lane dropdown did not open; assuming "
              f"{current} is this champion's only role")
        return [current], [], nodes, current
    labels: list[str] = []
    for node in options:
        label = node.label.strip()
        if label not in labels:
            labels.append(label)
    return labels, options, nodes, current


def _back_to_champion(client, depth: int = 2):
    """One level back, onto the champion page. Returns its dump, or None."""
    for _ in range(depth):
        client.back()
        nodes = _wait_for(client, *SIG_CHAMPION, timeout=4.0)
        if nodes is not None:
            return nodes
    return None


def capture_lane(client, champion: str, lane_cn: str, lane_en: str,
                 lanes_cn: list[str], args, nodes) -> tuple[str, list]:
    """Capture one lane of a champion, starting and ending on its page.

    Returns ("ok" or a short reason, the latest dump). Both filters are set
    BEFORE 查看更多, because the data page is built for whatever the champion
    page was set to: setting either afterwards would mean recapturing.
    """
    ok, nodes = set_lane(client, nodes, lane_cn)
    if not ok:
        return f"could not set lane to {lane_cn}", nodes
    ok, nodes = set_rank(client, nodes, args.bracket_cn)
    if not ok:
        return f"could not set rank to {args.bracket_cn}", nodes

    # From the dump the filters already produced, not a fresh one.
    more = uiauto.find(nodes, "查看更多")
    if more is None:
        return "no 查看更多 on the champion page", nodes
    client.tap(*more.center)

    # Measured at 7-10s on the device, so this gets its own generous budget.
    if _wait_for(client, *SIG_DATA, timeout=args.data_wait) is None:
        return (f"国服数据 never appeared (waited {args.data_wait:.0f}s)",
                _back_to_champion(client) or nodes)

    stamp = time.strftime("%Y%m%d_%H%M")
    out_dir = args.out / f"{champion.lower()}_{lane_en}_{args.bracket.lower()}_{stamp}"
    capture_champion(client, champion, out_dir, args.bracket, args.mode,
                     lane_en, lanes_available=lanes_cn)

    back = _back_to_champion(client)
    if back is None:
        return "stuck off the champion page after capture", nodes
    return "ok", back


def capture_one(client, node_label: str, champion: str, args,
                done: set, screen: tuple[int, int]) -> list[tuple[str, str]]:
    """Capture EVERY lane this champion offers, in one visit to its page.

    Returns [(lane, result)] for each lane attempted, result being "ok" or a
    short reason. Every path ends back on the hero list, because a walk that
    stops navigating but keeps tapping would capture the same screen for
    every remaining champion.

    One visit, all lanes: the champion appears in the hero list once per
    lane it is RANKED in, which is not the same set as the lanes its loadout
    panel breaks out, and reaching its page is the expensive part anyway.
    """
    def failed(reason: str) -> list[tuple[str, str]]:
        """Every exit from here says why, out loud. These three used to
        return a reason that nothing printed."""
        print(f"      ! {reason}")
        return [("?", reason)]

    nodes = uiauto.dump(client)
    # Being on the hero list is a precondition, not an assumption. Off it,
    # the name below matches a counter portrait instead of a row.
    if not uiauto.on_screen(nodes, *SIG_HERO_LIST):
        _back_to_list(client)
        nodes = uiauto.dump(client)
        if not uiauto.on_screen(nodes, *SIG_HERO_LIST):
            return failed("not on the hero list; cannot pick a champion")
    width, height = screen
    rows = uiauto.visible(nodes, width, height, LIST_TOP, LIST_BOTTOM)
    target = uiauto.find(rows, node_label, exact=True)
    if target is None:
        return failed("row scrolled out of view before the tap")
    client.tap(*target.center)

    nodes = _wait_for(client, *SIG_CHAMPION)
    if nodes is None:
        _back_to_list(client)
        return failed("champion page never appeared")

    lanes_cn, options, nodes, current_lane = lanes_for_champion(client, nodes)
    if not lanes_cn:
        _back_to_list(client)
        return failed("no lane filter on the champion page")
    if len(lanes_cn) > 1:
        print(f"    {len(lanes_cn)} roles: {' '.join(lanes_cn)}")

    # NOT filtered by --lanes. That argument chooses which hero-list tabs
    # to walk; once a champion's page is open, every role its dropdown
    # offers is captured. Filtering here as well meant --lanes dragon found
    # Vayne offering 上单 and ADC and kept only the ADC half, discarding a
    # role whose page was already loaded and already listed in the menu.
    wanted = []
    for lane_cn in lanes_cn:
        lane_en = L.LANES.get(lane_cn, lane_cn).lower()
        if (champion, lane_en) in done:
            print(f"    - {lane_en:8s} already captured")
            continue
        wanted.append((lane_cn, lane_en))

    # Spend the open dropdown on the first lane we actually want, rather
    # than closing it and reopening to pick the same thing. With nothing
    # wanted, reselect whatever was already set, purely to dismiss the menu.
    if options:
        first = wanted[0][0] if wanted else current_lane
        after = _commit(client, options, first, "lane") if first else None
        if after is None:
            client.back()
            after = uiauto.dump(client)
        nodes = after

    out: list[tuple[str, str]] = []
    for lane_cn, lane_en in wanted:
        print(f"    > {lane_en} ({lane_cn})")
        result, nodes = capture_lane(client, champion, lane_cn, lane_en,
                                     lanes_cn, args, nodes)
        out.append((lane_en, result))
        if result != "ok":
            print(f"      ! {result}")

    _back_to_list(client)
    return out


def _resume_set(out_dir: Path, bracket: str) -> tuple[set, set]:
    """((champion, lane) pairs on disk, champions with every lane done).

    The second set is what makes resuming cheap. Without it a rerun has to
    open each finished champion's page again just to learn how many lanes it
    has before it can decide there is nothing to do -- 141 page loads at
    7-10s each. Captures record lanesAvailable for exactly this, so a
    champion whose every listed lane is on disk is skipped from the list.
    """
    done, lanes_seen = set(), {}
    for d in out_dir.glob(f"*_{bracket.lower()}_*"):
        man = d / "manifest.json"
        if not man.exists():
            continue
        try:
            m = json.loads(man.read_text(encoding="utf-8"))
        except Exception:
            continue
        champion = m.get("champion")
        done.add((champion, m.get("lane")))
        available = m.get("lanesAvailable") or []
        if available:
            lanes_seen[champion] = available
    complete = {
        champion for champion, available in lanes_seen.items()
        if all((champion, L.LANES.get(cn, cn).lower()) in done for cn in available)
    }
    return done, complete


def walk(client, args) -> int:
    cn_map = _cn_names()
    labels = set(cn_map)
    skipped: dict[str, str] = {}
    done, complete = _resume_set(args.out, args.bracket)
    if done:
        print(f"resuming: {len(done)} (champion, lane) pairs already captured, "
              f"{len(complete)} champions complete")
    visited: set[str] = set()
    unknown: set[str] = set()

    wanted = [(cn, en) for cn, en in LANE_ORDER
              if not args.lanes or en in args.lanes]
    captured = failed = 0

    for lane_cn, lane_en in wanted:
        nodes = _wait_for(client, *SIG_HERO_LIST)
        if nodes is None:
            print("! not on the hero list; open 攻略 > 英雄榜 and rerun")
            return 2
        tab = uiauto.find(nodes, lane_cn, exact=True)
        if tab is None:
            print(f"! lane {lane_cn} not in the sidebar, skipping")
            continue
        client.tap(*tab.center)
        time.sleep(1.0)
        print(f"\n== lane {lane_cn} ({lane_en}) ==")

        height, width = client.screenshot().shape[:2]
        # The hierarchy carries the WHOLE lane, including rows scrolled out of
        # view, so this is the roster up front rather than a guess that we are
        # finished once scrolling stops revealing anybody.
        roster = {n.label.strip() for n in uiauto.find_all(uiauto.dump(client), labels)}
        print(f"   {len(roster)} champions in this lane")

        seen: set[str] = set()
        dry = 0
        while dry < DRY_SCROLLS and len(seen) < len(roster):
            nodes = uiauto.dump(client)
            # Tap targets must be ON SCREEN. find_all over the raw dump would
            # return rows sitting at y=5800 on a 2340-tall display.
            on_screen = uiauto.visible(nodes, width, height, LIST_TOP, LIST_BOTTOM)
            rows = [n for n in uiauto.find_all(on_screen, labels)
                    if n.label.strip() not in seen]
            if not rows:
                client.swipe(width // 2, int(height * 0.75),
                             width // 2, int(height * 0.35), 400)
                time.sleep(0.8)
                dry += 1
                continue
            dry = 0
            for node in rows:
                label = node.label.strip()
                seen.add(label)
                champion = cn_map.get(label)
                if champion is None:
                    # Never silent. A row the app lists and we cannot name
                    # is a new champion or a stale map, and the old bare
                    # `continue` is how Hwei disappeared without a trace.
                    if label not in unknown:
                        unknown.add(label)
                        print(f"  ? {label:16s} not in the champion name map, skipped")
                    continue
                # Skipped by CHAMPION, not by (champion, lane): one visit
                # captures every lane the champion offers, so meeting it
                # again under a second hero-list tab has nothing left to do.
                if champion in visited or champion in complete:
                    print(f"  - {champion:16s} already captured")
                    continue
                if champion in SKIP_CHAMPIONS:
                    print(f"  - {champion:16s} no data: {SKIP_CHAMPIONS[champion]}")
                    skipped[champion] = SKIP_CHAMPIONS[champion]
                    visited.add(champion)
                    continue
                print(f"  > [{len(seen)}/{len(roster)}] {champion} ({label})")
                results = capture_one(client, label, champion, args, done,
                                      (width, height))
                for lane_done, result in results:
                    if result == "ok":
                        captured += 1
                        done.add((champion, lane_done))
                    else:
                        failed += 1      # capture_one already said why
                # Visited means FINISHED, not attempted. A champion whose
                # lanes all failed here is left for the next hero-list tab
                # it appears under, which is a different route to the same
                # page and may well work -- and an empty result means every
                # lane was already on disk, which is finished too.
                if all(result == "ok" for _lane, result in results):
                    visited.add(champion)
                if args.limit and captured >= args.limit:
                    print(f"— stopping at --limit {args.limit}")
                    print(f"done: {captured} captured, {failed} failed")
                    return 0 if failed == 0 else 1

    if unknown:
        print(f"\n! {len(unknown)} hero-list row(s) had no champion name: "
              f"{' '.join(sorted(unknown))}")
        print("  add them to data/cn_winrates.json or to CN_NAME_OVERRIDES "
              "in src/ocr.py, then rerun.")
    _write_no_data(args.out, skipped)
    tail = f", {len(skipped)} with no data in the app" if skipped else ""
    print(f"\ndone: {captured} captured, {failed} failed{tail}")
    return 0 if failed == 0 else 1


def _write_no_data(out_dir: Path, skipped: dict[str, str]) -> None:
    """Record the champions the app cannot show, merging with earlier runs.

    Written even when this run skipped nothing new, so the file stays an
    accurate statement of the whole dataset rather than of one pass.
    """
    path = out_dir / NO_DATA_FILE
    known: dict[str, str] = {}
    if path.exists():
        try:
            known = json.loads(path.read_text(encoding="utf-8")).get("champions", {})
        except Exception:  # noqa: BLE001 -- a corrupt file must not end a walk
            known = {}
    known.update(skipped)
    if not known:
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "note": "Champions with no loadout data because the app does not show "
                "them. Absence here is deliberate, not a failed capture.",
        "champions": known,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    for champion, reason in sorted(known.items()):
        print(f"  no data: {champion} -- {reason}")


def _probe(nodes) -> int:
    """Show what the device reports, and whether it is enough to navigate."""
    if not nodes:
        print("uiautomator returned NOTHING. Navigation cannot work; use "
              "scripts.scrape_loadouts per champion instead.")
        return 2
    labelled = [n for n in nodes if n.label.strip()]
    print(f"{len(nodes)} nodes, {len(labelled)} carrying a label")
    cn_map = _cn_names()
    champions = [n for n in labelled if n.label.strip() in cn_map]
    print()
    print("labels on this screen:")
    for n in labelled[:40]:
        mark = "  <- champion" if n.label.strip() in cn_map else ""
        print(f"  {n.label.strip()[:28]:30s} @{n.center}{mark}")
    if len(labelled) > 40:
        print(f"  ... and {len(labelled) - 40} more")
    print()
    for sig, what in ((SIG_HERO_LIST, "hero list"), (SIG_CHAMPION, "champion page"),
                      (SIG_DATA, "国服数据")):
        if uiauto.on_screen(nodes, *sig):
            print(f"recognised this screen as: {what}")
    print(f"champion names in the hierarchy: {len(champions)}")
    if champions:
        ys = [n.center[1] for n in champions]
        print(f"  their y range: {min(ys)} .. {max(ys)}")
        print("  (a max far beyond the screen height is normal: Android lays "
              "out the whole list and clips it. Only the on-screen ones are "
              "tappable, which is what uiauto.visible filters to.)")
    if not champions:
        print("  (none -- on the hero list this would mean the rows are not "
              "exposed as text, and the walk cannot pick champions)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bracket", default=DEFAULT_BRACKET,
                    help="rank to SET on each champion page: diamond, master, "
                         "challenger or legendary (default: legendary, the "
                         "highest, shown in the app as 峡谷之巅)")
    ap.add_argument("--mode", default="",
                    help="the mode chip selected, e.g. 'classic-ranked'")
    ap.add_argument("--lanes", default="",
                    help="comma-separated subset of hero-list TABS to walk, "
                         "e.g. 'baron,jungle'; default walks all five. It "
                         "does not limit what is captured: every role a "
                         "champion's own lane dropdown offers is taken, so "
                         "walking one tab can still produce two captures for "
                         "a champion played in two lanes.")
    ap.add_argument("--device", default=ADBClient.device)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--data-wait", type=float, default=25.0,
                    help="seconds to wait for 国服数据 after tapping 查看更多 "
                         "(default 25). Each poll is a hierarchy dump, which "
                         "costs about 3s on this device, so 25 is roughly "
                         "eight looks. Raise it for a champion that loads "
                         "slowly rather than losing the capture.")
    ap.add_argument("--limit", type=int, default=0,
                    help="stop after this many captures. Use --limit 2 for a "
                         "smoke test before committing to the full roster.")
    ap.add_argument("--probe", action="store_true",
                    help="dump what the device reports on the current screen "
                         "and exit. Run this once before a full walk: if the "
                         "labels are not here, navigation cannot work.")
    args = ap.parse_args()
    args.lanes = {s.strip() for s in args.lanes.split(",") if s.strip()}
    args.bracket_cn = BRACKET_ALIASES.get(args.bracket.strip().lower(), "")
    if not args.probe and not args.bracket_cn:
        print(f"unknown --bracket {args.bracket!r}; expected one of "
              f"{sorted(set(BRACKET_ALIASES))}", file=sys.stderr)
        return 2

    client = ADBClient(device=args.device)
    try:
        client.connect()
    except ADBError as exc:
        print(f"adb: {exc}", file=sys.stderr)
        return 2

    nodes = uiauto.dump(client)
    if args.probe:
        return _probe(nodes)

    if not args.mode:
        print("--mode is required (it is the provenance that makes the "
              "numbers comparable). Use --probe alone to test the connection.",
              file=sys.stderr)
        return 2

    if not nodes:
        print("uiautomator returned nothing. The device may not support it, "
              "or the app blocks it. Navigation needs it; capture does not, "
              "so scripts.scrape_loadouts still works one champion at a time.",
              file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    lanes_label = "all" if not args.lanes else ",".join(sorted(args.lanes))
    print(f"walking: bracket={args.bracket} ({args.bracket_cn}) "
          f"mode={args.mode} lanes={lanes_label}")
    print("(the rank is set per champion; you only need the 经典 chip and the "
          "lane set before starting)")
    return walk(client, args)


if __name__ == "__main__":
    raise SystemExit(main())
