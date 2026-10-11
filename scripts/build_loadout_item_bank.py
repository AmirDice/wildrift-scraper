"""Teach the item bank what items look like in the LOADOUT panel.

The catalogue art matches a loadout equip icon about half the time: 17 of
33 on the benchmark capture, and the residue fails on SCORE rather than
on ties, which is the signature of art that genuinely differs rather than
of a gate set too tight. Same story the rune bank already told -- the
game draws its own icons at its own zoom, on its own backgrounds, and no
amount of threshold tuning closes that.

The rune bank was built from owner-labelled clusters because nothing
could name a rune automatically. Items do not need that: the catalogue
already matches HALF of them, so a cluster of the same item seen two
hundred times across the roster usually contains several confident
reads, and those name the cluster for the rest. Where they do not, the
cluster is reported rather than guessed at, and can be named by hand the
way the runes were.

    python -m scripts.build_loadout_item_bank --dry-run   # what it would learn
    python -m scripts.build_loadout_item_bank             # write the bank

Templates are ADDED to data/icon_bank/items.npz under "<name>#ld<n>"
keys. match_slot folds a suffixed key into its base name, so a new look
at an item is another chance to recognise it and never a second item.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import loadouts as L  # noqa: E402
from src import icon_match  # noqa: E402

CAPTURES = ROOT / "data" / "captures_loadouts"
BANK = ROOT / "data" / "icon_bank" / "items.npz"

#: Tabs whose entity column holds ITEM icons.
ITEM_TABS = ("equip", "boots")

#: Cosine similarity above which two icons are the same item. High on
#: purpose: a cluster that merges two items poisons every template it
#: contributes, while an item split across two clusters costs nothing but
#: a second entry, and match_slot folds those back together anyway.
JOIN = 0.90

#: A cluster is named only on this much agreement among the reads that
#: were confident enough to produce a name at all.
MIN_VOTES = 3
MIN_SHARE = 0.60

#: Templates kept per item. The members furthest apart are the useful
#: ones -- near-duplicates of a template already in the bank teach it
#: nothing -- so this caps the bank's growth without losing coverage.
PER_ITEM = 4


def _vector(tile: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """A tile as a unit vector, weighted and mean-removed like _score."""
    flat = []
    for ch in range(3):
        x = tile[:, :, ch]
        xd = (x - (x * weights).sum() / weights.sum()) * weights
        flat.append(xd.ravel())
    v = np.concatenate(flat)
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-6 else v


def harvest(limit: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """[(normalised tile, unit vector)] for every item icon on disk."""
    weights = icon_match._weights(True, False)
    out = []
    folders = sorted(d for d in CAPTURES.iterdir()
                     if (d / "manifest.json").is_file())
    if limit:
        folders = folders[:limit]
    for folder in folders:
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        for tab in ITEM_TABS:
            info = manifest["tabs"].get(tab)
            if not info or not info["frames"]:
                continue
            # The first frame of each tab is enough: later frames are the
            # same table scrolled, so they repeat items already seen.
            image = cv2.imread(str(folder / info["frames"][0]))
            if image is None:
                continue
            for row in L.find_rows(image):
                cells = L.row_cells(image, row)
                for icon in L.segment_icons(cells["entity"], L.TABS[tab]["icons"]):
                    if icon.size == 0:
                        continue
                    tile = icon_match._norm_tile(icon)
                    out.append((tile, _vector(tile, weights)))
    return out


def cluster(samples) -> list[list[int]]:
    """Greedy single-pass clustering on cosine similarity."""
    centres: list[np.ndarray] = []
    members: list[list[int]] = []
    # Centres also live stacked, so each sample is one matrix-vector
    # product instead of a Python loop over several hundred centres. At
    # six thousand icons that is the difference between minutes and
    # seconds, and it computes exactly the same similarities.
    stack: np.ndarray | None = None
    for i, (_tile, vec) in enumerate(samples):
        if centres:
            sims = stack @ vec
            best = int(sims.argmax())
            if sims[best] >= JOIN:
                members[best].append(i)
                n = len(members[best])
                centres[best] = centres[best] * ((n - 1) / n) + vec / n
                norm = float(np.linalg.norm(centres[best]))
                if norm > 1e-6:
                    centres[best] /= norm
                stack[best] = centres[best]
                continue
        centres.append(vec.copy())
        members.append([i])
        stack = (vec[None, :].copy() if stack is None
                 else np.vstack([stack, vec[None, :]]))
    return members


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be learned, write nothing")
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N captures, for a quick look")
    args = ap.parse_args()

    print("harvesting item icons from the loadout captures ...")
    samples = harvest(args.limit)
    if not samples:
        print("no item icons found", file=sys.stderr)
        return 2
    print(f"  {len(samples)} icons")

    groups = cluster(samples)
    groups.sort(key=len, reverse=True)
    print(f"  {len(groups)} clusters "
          f"(largest {len(groups[0])}, singletons "
          f"{sum(1 for g in groups if len(g) == 1)})")

    print("naming clusters from the reads the catalogue IS sure about ...")
    named: dict[str, list[int]] = defaultdict(list)
    unnamed = 0
    for group in groups:
        votes = Counter()
        # Sampling, not every member: a cluster of 200 identical icons
        # answers the same way on the tenth as on the two hundredth.
        for idx in group[:12]:
            name, score, _gap, _ru = icon_match.match_slot(samples[idx][0], "items")
            if name != "?" and score >= icon_match.MIN_SCORE:
                votes[name] += 1
        total = sum(votes.values())
        if total >= MIN_VOTES:
            best, count = votes.most_common(1)[0]
            if count / total >= MIN_SHARE:
                named[best].extend(group)
                continue
        unnamed += 1

    print(f"  named {len(named)} items from {len(groups) - unnamed} clusters; "
          f"{unnamed} clusters unnamed")

    # Pick the most DISSIMILAR members per item: a template that looks like
    # one already in the bank adds nothing to recognise with.
    additions: dict[str, np.ndarray] = {}
    for name, idxs in sorted(named.items()):
        chosen: list[int] = []
        for idx in idxs:
            if len(chosen) >= PER_ITEM:
                break
            vec = samples[idx][1]
            if all(float(vec @ samples[c][1]) < JOIN for c in chosen):
                chosen.append(idx)
        for n, idx in enumerate(chosen):
            additions[f"{name}#ld{n}"] = samples[idx][0]

    print(f"  {len(additions)} templates for {len(named)} items")
    if args.dry_run:
        for name in sorted(named)[:15]:
            print(f"    {name:28s} {len(named[name]):4d} icons")
        print("dry run: nothing written")
        return 0

    existing = {}
    if BANK.exists():
        with np.load(BANK) as z:
            existing = {k: z[k] for k in z.files}
        print(f"  existing bank: {len(existing)} templates (kept)")
    existing.update(additions)
    BANK.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BANK, **existing)
    print(f"wrote {BANK.relative_to(ROOT)} ({len(existing)} templates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
