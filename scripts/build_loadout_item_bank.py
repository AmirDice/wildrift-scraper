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


FROZEN = ROOT / "data" / "icon_bank" / "loadout_item_clusters.npz"
LABELS = ROOT / "data" / "loadout_item_labels.json"
SHEET = ROOT / "data" / "debug_scans" / "_loadout_items_to_name.png"

#: Clusters smaller than this are left off the sheet. They are
#: overwhelmingly mis-segmented fragments and half-icons rather than rare
#: items -- of 509 clusters, 231 were singletons -- and putting 500 cells
#: in front of a person to find 130 real ones is how a naming pass gets
#: abandoned. Raise it to see fewer, pass 1 to see everything.
SHEET_MIN_SIZE = 3


def freeze(samples, groups) -> dict:
    """Number the clusters once and write them down, with one tile each.

    The stored art is the member CLOSEST to its cluster's centre, which
    is the cleanest look at that item rather than whichever instance
    happened to be first.
    """
    art, sizes, names = [], [], []
    for group in groups:
        vecs = np.stack([samples[i][1] for i in group])
        centre = vecs.mean(axis=0)
        norm = float(np.linalg.norm(centre))
        if norm > 1e-6:
            centre = centre / norm
        best = group[int((vecs @ centre).argmax())]
        art.append(samples[best][0])
        sizes.append(len(group))
        names.append(auto_name(samples, group) or "")
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(FROZEN, art=np.stack(art),
                        sizes=np.array(sizes),
                        guesses=np.array(names, dtype=object),
                        members=np.array(
                            [np.array(g, dtype=np.int32) for g in groups],
                            dtype=object))
    return {"art": np.stack(art), "sizes": sizes, "guesses": names}


def load_frozen() -> dict | None:
    if not FROZEN.exists():
        return None
    with np.load(FROZEN, allow_pickle=True) as z:
        return {"art": z["art"], "sizes": list(z["sizes"]),
                "guesses": [str(g) for g in z["guesses"]]}


def owner_labels() -> dict[str, str]:
    if not LABELS.exists():
        return {}
    data = json.loads(LABELS.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items()
            if not k.startswith("_") and isinstance(v, str) and v.strip()}


def auto_name(samples, group) -> str | None:
    """The catalogue's own verdict on a cluster, or None if it has none."""
    votes = Counter()
    for idx in group[:12]:
        name, score, _gap, _ru = icon_match.match_slot(samples[idx][0], "items")
        if name != "?" and score >= icon_match.MIN_SCORE:
            votes[name] += 1
    total = sum(votes.values())
    if total < MIN_VOTES:
        return None
    best, count = votes.most_common(1)[0]
    return best if count / total >= MIN_SHARE else None


def write_sheet(frozen: dict) -> int:
    """A numbered contact sheet, biggest clusters first."""
    owner = owner_labels()
    order = sorted(range(len(frozen["sizes"])),
                   key=lambda k: -frozen["sizes"][k])
    order = [k for k in order if frozen["sizes"][k] >= SHEET_MIN_SIZE]
    cells = []
    for k in order:
        cell = np.full((164, 118, 3), (26, 20, 15), np.uint8)
        tile = cv2.resize(frozen["art"][k].astype(np.uint8), (100, 100))
        cell[6:106, 9:109] = tile
        number = str(k + 1)                  # 1-based, as on the rune sheet
        cv2.putText(cell, number, (6, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.62, (0, 0, 0), 4)
        cv2.putText(cell, number, (6, 24), cv2.FONT_HERSHEY_SIMPLEX,
                    0.62, (80, 220, 255), 1)
        have = owner.get(number) or frozen["guesses"][k]
        for j, txt in enumerate([(have or "UNNAMED")[:17],
                                 f"n={frozen['sizes'][k]}"]):
            col = (150, 240, 160) if (j == 0 and have) else (140, 140, 150)
            cv2.putText(cell, txt, (5, 124 + j * 16), cv2.FONT_HERSHEY_SIMPLEX,
                        0.36, col, 1, cv2.LINE_AA)
        cells.append(cell)
    if not cells:
        print("no clusters big enough for the sheet", file=sys.stderr)
        return 2
    cols = 8
    while len(cells) % cols:
        cells.append(np.zeros((164, 118, 3), np.uint8))
    SHEET.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(SHEET), np.vstack([np.hstack(cells[i:i + cols])
                                       for i in range(0, len(cells), cols)]))
    named = sum(1 for k in order
                if owner.get(str(k + 1)) or frozen["guesses"][k])
    print(f"{len(order)} clusters (of {len(frozen['sizes'])}, "
          f"those with {SHEET_MIN_SIZE}+ icons) -> {SHEET.relative_to(ROOT)}")
    print(f"  {named} already have a name, {len(order) - named} say UNNAMED")
    print(f"  put names in {LABELS.relative_to(ROOT)} keyed by the number "
          f"printed on each cell, then rerun without --sheet")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be learned, write nothing")
    ap.add_argument("--limit", type=int, default=0,
                    help="only the first N captures, for a quick look")
    ap.add_argument("--sheet", action="store_true",
                    help="write the numbered naming sheet and stop")
    ap.add_argument("--recluster", action="store_true",
                    help="recompute the clusters. INVALIDATES every name in "
                         "the labels file, because the numbers move.")
    args = ap.parse_args()

    frozen = None if args.recluster else load_frozen()
    if frozen is not None and args.sheet:
        return write_sheet(frozen)

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

    if args.recluster and FROZEN.exists():
        print("  RECLUSTERED: every number in "
              f"{LABELS.relative_to(ROOT)} now points somewhere else and "
              "must be reviewed against a fresh sheet.")
    frozen = freeze(samples, groups)
    print(f"  numbering frozen -> {FROZEN.relative_to(ROOT)}")
    if args.sheet:
        return write_sheet(frozen)

    print("naming clusters: owner labels first, catalogue reads second ...")
    owner = owner_labels()
    named: dict[str, list[int]] = defaultdict(list)
    from_owner = unnamed = 0
    for k, group in enumerate(groups):
        # The owner's word beats the machine's: a hand-written label only
        # exists because somebody looked at the icon.
        label = owner.get(str(k + 1)) or frozen["guesses"][k]
        if owner.get(str(k + 1)):
            from_owner += 1
        if label:
            named[label].extend(group)
        else:
            unnamed += 1

    print(f"  named {len(named)} items from {len(groups) - unnamed} clusters "
          f"({from_owner} by hand); {unnamed} clusters unnamed")

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
