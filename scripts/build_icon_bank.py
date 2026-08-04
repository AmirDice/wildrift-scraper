"""Build the rune template bank from the game's own rendering.

The catalogue art we ship is drawn differently from what Wild Rift puts on a
build popup -- different zoom, square instead of circular, different
backgrounds -- so matching a popup against it tops out around 3/5 even after
multi-scale and contrast tuning. The game's own pixels have no such gap.

So: crop every rune slot out of every captured popup, cluster them (identical
runes land together), and name each cluster ONCE. Two sources of names, no
guessing:
  - clusters where the vision model already agreed with itself on a real rune
    at >=70% are auto-labelled (Conqueror 100%, Manaflow Band 98%, ...);
  - the rest were named by the owner from a contact sheet, in
    data/rune_cluster_labels.json.

The result is data/icon_bank/runes.npz: one averaged template per rune, in the
game's own rendering, which src/icon_match.py matches against exactly.

    python -m scripts.build_icon_bank            # build the bank
    python -m scripts.build_icon_bank --sheet    # regenerate the naming sheet
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.icon_match import GEOMETRY, N  # noqa: E402
from web.runes import canonical_rune, is_known_rune  # noqa: E402

BANK = ROOT / "data" / "icon_bank"
LABELS = ROOT / "data" / "rune_cluster_labels.json"
SHEET = ROOT / "data" / "debug_scans" / "_runes_to_name.png"
CLUSTER_THRESHOLD = 0.30      # correlation distance; tuned on real captures
MIN_CLUSTER = 5
AUTO_AGREE = 0.70             # model self-agreement needed to trust a name


def _mask() -> np.ndarray:
    yy, xx = np.mgrid[0:N, 0:N]
    r = np.sqrt((yy - (N - 1) / 2) ** 2 + (xx - (N - 1) / 2) ** 2)
    m = r <= N * 0.38
    m[int(N * 0.66):, :int(N * 0.58)] = False   # the game's "upgraded" pip
    return m


def collect() -> tuple[np.ndarray, list, list]:
    """(feature matrix, [(session, rank, slot)], [raw tile]) for every rune slot."""
    y0, size, x0, pitch, count = GEOMETRY["runes"]
    m = _mask()
    feats, meta, raw = [], [], []
    for f in sorted(glob.glob(str(ROOT / "data" / "captures" / "*" / "0*_build.jpg"))):
        img = cv2.imread(f)
        if img is None or img.shape[:2] != (1080, 2340):
            continue
        session, rank = os.path.dirname(f), int(os.path.basename(f).split("_")[0])
        for i in range(count):
            tile = img[y0:y0 + size, x0 + i * pitch: x0 + i * pitch + size]
            if tile.size == 0:
                continue
            small = cv2.resize(tile, (N, N), interpolation=cv2.INTER_AREA)
            v = small.astype(np.float32)[m].flatten()
            feats.append((v - v.mean()) / (v.std() + 1e-6))
            meta.append((session, rank, i))
            raw.append(tile)
    return np.array(feats, np.float32), meta, raw


def model_said(meta: list) -> dict:
    """What the vision model called each slot, canonicalised."""
    out: dict = {}
    for session in {m[0] for m in meta}:
        p = os.path.join(session, "builds.jsonl")
        if not os.path.exists(p):
            continue
        for line in open(p, encoding="utf-8"):
            b = json.loads(line)
            for i, r in enumerate(b.get("runes") or []):
                out[(session, b["rank"], i)] = canonical_rune(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", action="store_true", help="write the naming contact sheet")
    args = ap.parse_args()

    X, meta, raw = collect()
    if not len(X):
        raise SystemExit("no build popups captured yet")
    D = pdist(X, "correlation")
    labels = fcluster(linkage(D, "average"), CLUSTER_THRESHOLD, "distance")
    Dsq = squareform(D)
    said = model_said(meta)

    clusters = [c for c in sorted(set(labels), key=lambda c: -(labels == c).sum())
                if (labels == c).sum() >= MIN_CLUSTER]
    auto, manual = {}, []
    for c in clusters:
        idx = np.where(labels == c)[0]
        names = Counter(n for i in idx if (n := said.get(meta[i])))
        total = sum(names.values())
        top, hits = names.most_common(1)[0] if names else (None, 0)
        if top and is_known_rune(top) and total and hits / total >= AUTO_AGREE:
            auto[c] = top
        else:
            manual.append(c)

    if args.sheet:
        cells = []
        for k, c in enumerate(manual, 1):
            idx = np.where(labels == c)[0]
            med = idx[Dsq[np.ix_(idx, idx)].sum(1).argmin()]
            im = cv2.resize(raw[med], (100, 100))
            cv2.putText(im, str(k), (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
            cv2.putText(im, str(k), (4, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (80, 220, 255), 1)
            cells.append(im)
        cols = 7
        while len(cells) % cols:
            cells.append(np.zeros((100, 100, 3), np.uint8))
        SHEET.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(SHEET), np.vstack([np.hstack(cells[i:i + cols])
                                           for i in range(0, len(cells), cols)]))
        print(f"{len(manual)} clusters need names -> {SHEET.relative_to(ROOT)}")
        return 0

    owner = json.loads(LABELS.read_text(encoding="utf-8"))["labels"] if LABELS.exists() else {}
    named: dict[int, str] = dict(auto)
    for k, c in enumerate(manual, 1):
        name = owner.get(str(k))
        if name:
            named[c] = canonical_rune(name)

    # One averaged template per rune, in the game's own rendering. Averaging
    # over every tile of that rune cancels JPEG noise and overlay variation.
    by_name: dict[str, list[int]] = {}
    for c, name in named.items():
        by_name.setdefault(name, []).extend(np.where(labels == c)[0].tolist())

    bank: dict[str, np.ndarray] = {}
    for name, idxs in by_name.items():
        stack = np.stack([cv2.resize(raw[i], (N, N), interpolation=cv2.INTER_AREA)
                          for i in idxs]).astype(np.float32)
        bank[name] = stack.mean(axis=0)

    BANK.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(BANK / "runes.npz", **{k: v for k, v in bank.items()})
    covered = sum(len(v) for v in by_name.values())
    print(f"clusters: {len(clusters)} ({len(auto)} auto-named, {len(manual)} owner-named)")
    print(f"runes in bank: {len(bank)}")
    print(f"tiles covered: {covered}/{len(X)} ({covered / len(X) * 100:.1f}%)")
    unnamed = [c for c in clusters if c not in named]
    if unnamed:
        print(f"still unnamed clusters: {len(unnamed)} "
              f"({sum((labels == c).sum() for c in unnamed)} tiles)")
    print(f"wrote {(BANK / 'runes.npz').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
