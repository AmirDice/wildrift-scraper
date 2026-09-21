"""The order the top 50 BUY their items in, not just which items they buy.

WHY THIS EXISTS

    The ladder consensus counted items and forgot where they sat. Every build
    was reduced to a sorted tuple of slugs before counting, so the "most built
    by server" card numbered items by POPULARITY -- "1. Serylda's Grudge" meant
    most-built, not bought-first -- while looking exactly like a purchase order.

    The order was never lost at the source. The build popup lists a player's
    items in inventory slot order, and Wild Rift fills the first free slot when
    an item is bought, so slot order is purchase order. Measured over the 6,890
    archived EU builds: Trinity Force is the first item 43% of the time and in
    the first two 74%; Guardian Angel is the LAST item 74% of the time;
    Rabadon's peaks fourth; boots are first or second in 63% of builds. Those
    are the orders players describe, which is what makes the slots trustworthy.

HOW THE ORDER IS DECIDED

    Not by averaging positions. An average is dragged around by who built what:
    a player who skipped the usual first item shifts everything they did buy
    one slot left, and the mean reports a blend of two different builds.

    Instead, a pairwise vote. For every two items in the shown build, look only
    at the players who built BOTH and count which one came first. An item's
    score is how many of those head-to-heads it wins (Copeland); ties fall back
    to the mean slot, then to how many players built it. "Trinity before
    Serylda's" is then a claim about players who actually bought both, which is
    the only honest version of it.

WHICH ITEMS

    Exactly the six the site shows: the five most-built non-boot items and the
    most-built boots, the same rule as ladderConsensusBuild in
    web-next/src/lib/ladder-build.ts. The order is only ever claimed over items
    the card actually displays.

USAGE

    build_ladder_pulse.py calls purchase_order() whenever a collection has
    builds, so a new builds capture carries its order automatically.

    For data whose builds were collected earlier and carried forward, the order
    can be recovered from the published per-player files in git:

        python -m scripts.ladder_item_order --from-git b1c0a3e

    It prefers builds that reproduce the consensus counts EXACTLY -- the proof
    that the order and the counts came from the same fifty players -- and
    records that as orderFrom "same". When a champion's consensus came from a
    capture whose per-player records no longer exist (33 champions on the
    2026-08 board: their session was overwritten by the next win-rate-only
    collection), the neighbouring snapshot of the SAME board is used instead,
    recorded as orderFrom "adjacent", and only if every item the card shows was
    bought by at least MIN_COVER of those players. Purchase order is a stable
    property of how a champion is built; it is not trusted for an item the
    fallback players barely bought.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.integrity import counts_toward_aggregates  # noqa: E402

CONSENSUS = ROOT / "data" / "ladder_consensus.json"
#: An adjacent snapshot must show each displayed item in at least this many
#: builds before its order is trusted. Five is where a pairwise vote stops
#: being one or two players' habit.
MIN_COVER = 5
PLAYERS = "web-next/public/players"

_CATEGORY = {i["slug"]: i.get("category") for i in
             json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}


def is_boots(slug: str) -> bool:
    return _CATEGORY.get(slug) == "Boots"


def shown_items(counted: list[tuple[str, int]]) -> list[str] | None:
    """The six the card renders, most-built first: five non-boot items and the
    top boots. None when there are not five non-boot items, which is when the
    site renders nothing either."""
    items: list[str] = []
    boots = None
    for slug, _count in counted:
        if is_boots(slug):
            boots = boots or slug
            continue
        if len(items) < 5:
            items.append(slug)
    if len(items) < 5:
        return None
    return items + ([boots] if boots else [])


def purchase_order(sequences: list[list[str]], shown: list[str]) -> tuple[list[str], dict[str, float]]:
    """`shown` reordered by the pairwise vote, and each item's mean 1-based slot.

    `sequences` are individual players' items in slot order.
    """
    first: Counter = Counter()          # (a, b) -> players who bought a before b
    slots: dict[str, list[int]] = {s: [] for s in shown}
    built: Counter = Counter()
    for seq in sequences:
        pos = {}
        for i, slug in enumerate(seq, 1):
            pos.setdefault(slug, i)      # a duplicate keeps its first slot
        for slug in shown:
            if slug in pos:
                slots[slug].append(pos[slug])
                built[slug] += 1
        for a, b in combinations(shown, 2):
            if a in pos and b in pos:
                if pos[a] < pos[b]:
                    first[(a, b)] += 1
                else:
                    first[(b, a)] += 1
    score: Counter = Counter()
    for a, b in combinations(shown, 2):
        ab, ba = first[(a, b)], first[(b, a)]
        if ab > ba:
            score[a] += 1
        elif ba > ab:
            score[b] += 1
        elif ab:                         # a real tie, not an absence of evidence
            score[a] += 0.5
            score[b] += 0.5
    mean = {s: (sum(v) / len(v) if v else 9.0) for s, v in slots.items()}
    ordered = sorted(shown, key=lambda s: (-score[s], mean[s], -built[s]))
    return ordered, {s: round(mean[s], 2) for s in shown}


def _git_players(rev: str) -> dict[str, list[list[str]]]:
    """{champion name: [ordered slugs per counted player]} from the per-player
    files published at `rev`."""
    listing = subprocess.run(["git", "ls-tree", "--name-only", f"{rev}:{PLAYERS}"],
                             cwd=ROOT, capture_output=True, text=True, check=True).stdout
    out: dict[str, list[list[str]]] = {}
    for name in listing.split():
        if not name.endswith(".json"):
            continue
        raw = subprocess.run(["git", "show", f"{rev}:{PLAYERS}/{name}"], cwd=ROOT,
                             capture_output=True, check=True).stdout.decode("utf-8")
        payload = json.loads(raw)
        seqs = []
        for p in payload.get("players", []):
            build = p.get("build") or {}
            # the same exclusion the counts were made under (web/integrity.py)
            if not counts_toward_aggregates(p.get("p") or p.get("player") or ""):
                continue
            slugs = [i.get("slug") for i in (build.get("items") or [])
                     if isinstance(i, dict) and i.get("slug") and i.get("name") != "?"]
            if slugs:
                seqs.append(slugs)
        if seqs:
            out[payload.get("champion") or name[:-5]] = seqs
    return out


def backfill(rev: str, dry_run: bool = False) -> int:
    consensus = json.loads(CONSENSUS.read_text(encoding="utf-8"))
    recovered = _git_players(rev)
    wrote = mismatched = missing = adjacent = 0
    for champ, rec in consensus.items():
        counted = [(i["slug"], i["count"]) for i in rec.get("items") or []]
        shown = shown_items(counted)
        seqs = recovered.get(champ)
        if not shown or not seqs:
            missing += 1
            continue
        # Provenance first: builds that reproduce the counts this card already
        # shows, item for item, are the same fifty players.
        recount = Counter(s for seq in seqs for s in set(seq))
        if all(recount.get(slug, 0) == count for slug, count in counted):
            source = "same"
        elif min(recount.get(slug, 0) for slug in shown) >= MIN_COVER:
            source = "adjacent"
        else:
            mismatched += 1
            thin = [f"{slug} {recount.get(slug, 0)}" for slug in shown if recount.get(slug, 0) < MIN_COVER]
            print(f"  {champ}: no matching builds, and the adjacent ones barely cover {', '.join(thin)}; left unordered")
            continue
        order, slot = purchase_order(seqs, shown)
        rec["order"] = order
        rec["orderFrom"] = source
        adjacent += source == "adjacent"
        for item in rec["items"]:
            if item["slug"] in slot:
                item["slot"] = slot[item["slug"]]
        wrote += 1
    print(f"ordered {wrote} champions from {rev} ({wrote - adjacent} from the same builds, "
          f"{adjacent} from the adjacent snapshot); {mismatched} left unordered, "
          f"{missing} had nothing to order")
    if not dry_run:
        CONSENSUS.write_text(json.dumps(consensus, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if not mismatched else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from-git", metavar="REV", required=True,
                    help="revision whose web-next/public/players/*.json carry the per-player builds")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    return backfill(args.from_git, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
