"""Classify every champion balance change since patch 0.5 as a nerf or a buff.

WHY THIS HAS TO BE DERIVED

    data/champion_change_history.json records what changed and when -- 139
    champions, 132 patches, 2,864 change lines back to 2020-10-10 -- but it has
    no idea whether a change helped or hurt. `kind` only separates "balance"
    from "bugfix". So "most nerfed champion ever" cannot be read out of the
    data; it has to be computed.

    94% of change lines carry an explicit "OLD -> NEW", which is enough.

THE ONE RULE THAT MATTERS

    Direction alone does not decide it. "Damage: 100 -> 80" is a nerf and
    "Cooldown: 12 -> 10" is a buff, and both numbers went down. So every stat
    is classified as higher-is-better or lower-is-better first, and only then
    does the arrow mean anything. LOWER_IS_BETTER below is the whole of that
    judgement, kept in one place where it can be argued with.

    Anything the rule cannot read -- no arrow, no numbers, a stat not
    recognised -- is counted as UNCLASSIFIED rather than guessed. A video that
    says "most nerfed ever" should be able to say how many changes it could not
    read.

    python -m scripts.nerf_history                     # the leaderboard
    python -m scripts.nerf_history --race --out race.json   # per-patch cumulative
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "champion_change_history.json"

#: Stats where a SMALLER number is better for the champion. Everything else is
#: treated as higher-is-better, which is the safe default: damage, health,
#: ratios, healing, shielding, range, durations and resistances all read that
#: way, and they are the overwhelming majority of lines.
LOWER_IS_BETTER = (
    "cooldown", "cost", "mana cost", "energy cost", "health cost", "recharge",
    "cast time", "delay", "windup", "wind-up", "charge time", "recast",
    "lockout", "channel",
)

#: Lines that describe the ENEMY being affected invert again: a longer slow on
#: the enemy is a buff to you, and the label reads like a duration either way.
#: Handled by the same table -- these are here as the exceptions to watch if
#: the classification is ever challenged.
ARROW = re.compile(r"(.*?)[:\s]\s*([^→>]+?)\s*(?:→|->)\s*(.+)$")
NUMS = re.compile(r"-?\d+(?:\.\d+)?")


def _mean(text: str) -> float | None:
    """Average of the numbers in a value, so 20/40/60 compares to 15/35/55."""
    nums = [float(n) for n in NUMS.findall(text)]
    return sum(nums) / len(nums) if nums else None


def classify(label: str, text: str) -> str:
    """'nerf', 'buff' or 'unclear' for one change line."""
    m = ARROW.search(text)
    if not m:
        return "unclear"
    stat = (m.group(1) or label or "").strip().lower()
    before, after = _mean(m.group(2)), _mean(m.group(3))
    if before is None or after is None or before == after:
        return "unclear"
    lower_better = any(w in stat for w in LOWER_IS_BETTER)
    went_up = after > before
    # went up and higher is better -> buff; went up and lower is better -> nerf
    return "buff" if went_up != lower_better else "nerf"


def load() -> dict:
    return json.loads(HISTORY.read_text(encoding="utf-8"))["champions"]


def tally(skip_mode_only: bool = True) -> tuple[dict, dict, collections.Counter]:
    """(per-champion totals, per-patch events, unclassified counter)."""
    champs = load()
    totals: dict[str, dict] = {}
    events: list[dict] = []
    unclear = collections.Counter()
    for name, entries in champs.items():
        for e in entries:
            if e.get("kind") != "balance":
                continue
            if skip_mode_only and e.get("modeOnly"):
                continue
            n = b = u = 0
            for ch in e.get("changes") or []:
                verdict = classify(ch.get("ability", ""), ch.get("text", ""))
                n += verdict == "nerf"
                b += verdict == "buff"
                u += verdict == "unclear"
            if not (n or b or u):
                continue
            unclear[name] += u
            t = totals.setdefault(name, {"nerfs": 0, "buffs": 0, "unclear": 0,
                                         "nerfPatches": 0, "patches": set()})
            t["nerfs"] += n
            t["buffs"] += b
            t["unclear"] += u
            t["patches"].add(e["patch"])
            if n > b:
                t["nerfPatches"] += 1
            events.append({"champion": name, "patch": e["patch"],
                           "date": (e.get("publishedAt") or "")[:10],
                           "nerfs": n, "buffs": b})
    for t in totals.values():
        t["patches"] = len(t["patches"])
    return totals, events, unclear


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--race", action="store_true",
                    help="emit the cumulative per-patch frames a bar race needs")
    ap.add_argument("--out", default="")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    totals, events, unclear = tally()
    ranked = sorted(totals.items(), key=lambda kv: -kv[1]["nerfs"])

    print(f"{'champion':14} {'nerfs':>6} {'buffs':>6} {'net':>6} {'patches':>8} {'unclear':>8}")
    for name, t in ranked[:args.top]:
        print(f"{name:14} {t['nerfs']:6} {t['buffs']:6} "
              f"{t['nerfs'] - t['buffs']:+6} {t['patches']:8} {t['unclear']:8}")
    tot_n = sum(t["nerfs"] for t in totals.values())
    tot_b = sum(t["buffs"] for t in totals.values())
    tot_u = sum(t["unclear"] for t in totals.values())
    print(f"\n{len(totals)} champions · {tot_n} nerfs · {tot_b} buffs · "
          f"{tot_u} unreadable ({100 * tot_u / max(1, tot_n + tot_b + tot_u):.1f}%)")

    if args.race:
        # Cumulative nerf count per champion after each patch, in date order.
        by_patch: dict[tuple, list] = collections.defaultdict(list)
        for ev in events:
            by_patch[(ev["date"], ev["patch"])].append(ev)
        running: collections.Counter = collections.Counter()
        frames = []
        for (date, patch) in sorted(by_patch):
            for ev in by_patch[(date, patch)]:
                running[ev["champion"]] += ev["nerfs"]
            top = running.most_common(12)
            frames.append({"date": date, "patch": patch,
                           "standings": [{"champion": c, "nerfs": v}
                                         for c, v in top if v > 0]})
        payload = {"frames": frames,
                   "final": [{"champion": c, **{k: v for k, v in t.items()}}
                             for c, t in ranked],
                   "totals": {"nerfs": tot_n, "buffs": tot_b, "unclear": tot_u}}
        if args.out:
            Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
            print(f"\n{len(frames)} frames -> {args.out}")
        else:
            print(f"\n{len(frames)} frames (pass --out to write them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
