"""Build the rune template bank from the game's own rendering.

The catalogue art we ship is drawn differently from what Wild Rift puts on a
build popup -- different zoom, square instead of circular, different
backgrounds -- so matching a popup against it tops out around 3/5 even after
multi-scale and contrast tuning. The game's own pixels have no such gap: a
tile matched against a template built from other captures of the same rune
scores 0.94-0.999.

So: crop every rune slot out of every captured popup, cluster them (identical
runes land together), and name each cluster ONCE.

NUMBERING IS FROZEN ON DISK. The clusters are computed once and saved to
data/icon_bank/rune_clusters.npz; every later run reuses them. This is not an
optimisation -- re-clustering after new captures landed silently renumbered
the naming sheet, so labels attached to neighbouring icons and the bank
learned wrong names. Only --recluster recomputes, and it warns that the
labels must be reviewed again.

    python -m scripts.build_icon_bank --sheet      # numbered naming sheet
    python -m scripts.build_icon_bank              # build the bank
    python -m scripts.build_icon_bank --recluster  # after many new captures
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.icon_match import GEOMETRY, N  # noqa: E402
from web.runes import canonical_rune, is_known_rune  # noqa: E402

BANK = ROOT / "data" / "icon_bank"
LABELS = ROOT / "data" / "rune_cluster_labels.json"
SHEET = ROOT / "data" / "debug_scans" / "_runes_to_name.png"
FROZEN = BANK / "rune_clusters.npz"
CLUSTER_THRESHOLD = 0.30
MIN_CLUSTER = 5
AUTO_AGREE = 0.70


def _mask() -> np.ndarray:
    yy, xx = np.mgrid[0:N, 0:N]
    r = np.sqrt((yy - (N - 1) / 2) ** 2 + (xx - (N - 1) / 2) ** 2)
    m = r <= N * 0.38
    m[int(N * 0.66):, :int(N * 0.58)] = False   # the game's "upgraded" pip
    return m


def collect() -> tuple[np.ndarray, list, list]:
    """(features, [(session, rank, slot)], [raw tile]) for every rune slot."""
    y0, size, x0, pitch, count = GEOMETRY["runes"]
    m = _mask()
    feats, meta, raw = [], [], []
    # EVERY capture root, not just data/captures. The regional runs write to
    # data/captures_na (and will to _eu, _cn), and a glob pinned to the
    # original directory meant the bank never saw a single NA frame -- which
    # is how Legend: Haste, added in patch 7.3, stayed missing from the bank
    # while sitting in dozens of captured popups.
    roots = sorted(glob.glob(str(ROOT / "data" / "captures*")))
    files: list[str] = []
    for root in roots:
        files += glob.glob(os.path.join(root, "*", "0*_build.jpg"))
    for f in sorted(files):
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


def _cluster(X: np.ndarray, raw: list, meta: list) -> dict:
    """Cluster once and freeze: number, medoid art, and the model's guess.

    Numbers are assigned by descending cluster size with the medoid index as
    the tie-break, so the same input always yields the same numbering.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist, squareform

    D = pdist(X, "correlation")
    labels = fcluster(linkage(D, "average"), CLUSTER_THRESHOLD, "distance")
    Dsq = squareform(D)
    said = model_said(meta)

    entries = []
    for c in set(labels):
        idx = np.where(labels == c)[0]
        if len(idx) < MIN_CLUSTER:
            continue
        medoid = int(idx[Dsq[np.ix_(idx, idx)].sum(1).argmin()])
        names = Counter(n for i in idx if (n := said.get(meta[i])))
        total = sum(names.values())
        top, hits = names.most_common(1)[0] if names else ("", 0)
        entries.append({
            "size": len(idx), "medoid": medoid,
            "guess": top or "", "agree": (hits / total) if total else 0.0,
        })
    entries.sort(key=lambda e: (-e["size"], e["medoid"]))

    BANK.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        FROZEN,
        labels=labels,
        medoids=np.array([e["medoid"] for e in entries]),
        sizes=np.array([e["size"] for e in entries]),
        guesses=np.array([e["guess"] for e in entries]),
        agrees=np.array([e["agree"] for e in entries]),
        art=np.stack([cv2.resize(raw[e["medoid"]], (100, 100)) for e in entries]),
    )
    return {"labels": labels, "entries": entries}


def _load_frozen() -> dict | None:
    if not FROZEN.exists():
        return None
    z = np.load(FROZEN, allow_pickle=False)
    entries = [{"size": int(s), "medoid": int(m), "guess": str(g), "agree": float(a)}
               for s, m, g, a in zip(z["sizes"], z["medoids"], z["guesses"], z["agrees"])]
    return {"labels": z["labels"], "entries": entries, "art": z["art"]}


def _append_new(X, raw, conf, art, entries) -> int:
    """Group the tiles that matched nothing and append each as a new cluster.

    A frozen numbering is what keeps the owner's labels valid, so a new rune
    must EXTEND it rather than trigger --recluster, which renumbers all 51 and
    invalidates every label. Appending is safe precisely because main() assigns
    tiles by medoid ART rather than by index.
    """
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist, squareform

    idx = np.where(conf < 0.55)[0]
    if len(idx) < MIN_CLUSTER:
        print(f"only {len(idx)} unmatched tile(s); nothing new to add")
        return 0
    sub = X[idx]
    D = pdist(sub, "correlation")
    labels = fcluster(linkage(D, "average"), CLUSTER_THRESHOLD, "distance")
    Dsq = squareform(D)

    added = []
    for c in sorted(set(labels)):
        where = np.where(labels == c)[0]
        if len(where) < MIN_CLUSTER:
            continue
        medoid_local = int(where[Dsq[np.ix_(where, where)].sum(1).argmin()])
        added.append((int(idx[medoid_local]), len(where)))
    if not added:
        print(f"{len(idx)} unmatched tile(s), but none formed a group of "
              f"{MIN_CLUSTER}+ -- these look like noise, not a new rune")
        return 0

    z = np.load(FROZEN, allow_pickle=False)
    first = len(entries) + 1
    np.savez_compressed(
        FROZEN,
        labels=z["labels"],   # per-tile assignments from the ORIGINAL freeze;
                              # unused by the bank build, kept for provenance
        medoids=np.concatenate([z["medoids"], [m for m, _ in added]]),
        sizes=np.concatenate([z["sizes"], [n for _, n in added]]),
        guesses=np.concatenate([z["guesses"], [""] * len(added)]),
        agrees=np.concatenate([z["agrees"], [0.0] * len(added)]),
        art=np.concatenate([z["art"], np.stack(
            [cv2.resize(raw[m], (100, 100)) for m, _ in added])]),
    )
    print(f"appended {len(added)} cluster(s), numbered "
          f"{first}..{first + len(added) - 1}, from {len(idx)} unmatched tiles:")
    for k, (_m, n) in enumerate(added, first):
        print(f"  cluster {k}: {n} tiles")
    print(f"name them in {LABELS.relative_to(ROOT)} then re-run without --add-new")
    print("review the art first: python -m scripts.build_icon_bank --sheet")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", action="store_true", help="write the numbered naming sheet")
    ap.add_argument("--recluster", action="store_true",
                    help="recompute clusters; RENUMBERS everything, labels must be reviewed")
    ap.add_argument("--add-new", action="store_true",
                    help="append clusters for tiles matching nothing frozen, so a "
                         "NEW rune can be named without renumbering the existing "
                         "ones; prints the numbers to add to the labels file")
    args = ap.parse_args()

    X, meta, raw = collect()
    if not len(X):
        raise SystemExit("no build popups captured yet")

    frozen = None if args.recluster else _load_frozen()
    if frozen is None:
        if not args.recluster and FROZEN.exists():
            raise SystemExit("frozen clusters unreadable; pass --recluster to rebuild")
        print("clustering from scratch -- numbering will change, review the labels")
        frozen = _cluster(X, raw, meta)
        frozen["art"] = np.stack([cv2.resize(raw[e["medoid"]], (100, 100))
                                  for e in frozen["entries"]])
    entries = frozen["entries"]
    # Tiles are assigned to frozen clusters by matching the medoid ART, not by
    # index, so new captures simply join an existing rune instead of forcing a
    # renumber. That decoupling is what keeps the labels valid over time.
    art = frozen["art"]

    owner = json.loads(LABELS.read_text(encoding="utf-8")).get("labels", {}) if LABELS.exists() else {}

    if args.sheet:
        cells = []
        for k, e in enumerate(entries, 1):
            im = np.full((164, 118, 3), (26, 20, 15), np.uint8)
            im[6:106, 9:109] = frozen["art"][k - 1]
            cv2.putText(im, str(k), (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 4)
            cv2.putText(im, str(k), (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (80, 220, 255), 1)
            have = owner.get(str(k)) or (e["guess"] if e["agree"] >= AUTO_AGREE else "")
            lines = [(have or "UNNAMED")[:17], f"n={e['size']}"]
            for j, txt in enumerate(lines):
                col = (150, 240, 160) if (j == 0 and have) else (140, 140, 150)
                cv2.putText(im, txt, (5, 124 + j * 16), cv2.FONT_HERSHEY_SIMPLEX,
                            0.36, col, 1, cv2.LINE_AA)
            cells.append(im)
        cols = 8
        while len(cells) % cols:
            cells.append(np.zeros((164, 118, 3), np.uint8))
        SHEET.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(SHEET), np.vstack([np.hstack(cells[i:i + cols])
                                           for i in range(0, len(cells), cols)]))
        print(f"{len(entries)} clusters -> {SHEET.relative_to(ROOT)}")
        print("every cluster is numbered; the name under each is the current guess")
        return 0

    # Build the bank from owner labels only -- the model's guesses proved
    # unreliable even when self-consistent, so they no longer name anything.
    named: dict[int, str] = {}
    for k in range(1, len(entries) + 1):
        name = owner.get(str(k))
        if name and name.strip() and name.strip() != "?":
            named[k] = canonical_rune(name)

    # Assign EVERY collected tile (old and new) to its nearest frozen medoid.
    m = _mask()
    protos = np.stack([cv2.resize(a, (N, N), interpolation=cv2.INTER_AREA).astype(np.float32)[m].flatten()
                       for a in art])
    protos = (protos - protos.mean(axis=1, keepdims=True)) / (protos.std(axis=1, keepdims=True) + 1e-6)
    sims = X @ protos.T / X.shape[1]          # both sides already normalised
    best = sims.argmax(axis=1)
    conf = sims.max(axis=1)

    by_name: dict[str, list[int]] = {}
    unmatched = 0
    for i, (b, c) in enumerate(zip(best, conf)):
        if c < 0.55:                           # not clearly any known rune
            unmatched += 1
            continue
        name = named.get(int(b) + 1)
        if name:
            by_name.setdefault(name, []).append(i)

    if args.add_new:
        return _append_new(X, raw, conf, art, entries)

    bank = {name: np.stack([cv2.resize(raw[i], (N, N), interpolation=cv2.INTER_AREA)
                            for i in idxs]).astype(np.float32).mean(axis=0)
            for name, idxs in by_name.items()}

    # MERGE into the existing bank rather than replacing it. The bank is
    # derived, but its source is not reproducible: the capture sessions under
    # data/captures were cleaned of their JPEGs long ago and only their CSVs
    # survive, so a rebuild sees whatever frames happen to be on disk right
    # now. Replacing wholesale took a 52-rune bank down to the 20 runes
    # visible in one champion's 30 builds. A freshly computed template wins
    # for every rune we CAN see; the rest keep the one they already had.
    BANK.mkdir(parents=True, exist_ok=True)
    previous = {}
    if (BANK / "runes.npz").exists():
        with np.load(BANK / "runes.npz") as z:
            previous = {k: z[k] for k in z.files}
    kept = sorted(set(previous) - set(bank))
    merged = {**previous, **bank}
    np.savez_compressed(BANK / "runes.npz", **merged)
    covered = sum(len(v) for v in by_name.values())
    print(f"clusters: {len(entries)} ({len(named)} named by owner)")
    print(f"runes in bank: {len(merged)} "
          f"({len(bank)} rebuilt from current captures, {len(kept)} kept)")
    if kept:
        print(f"kept (no frames on disk any more): {', '.join(kept[:8])}"
              + (f" +{len(kept) - 8} more" if len(kept) > 8 else ""))
    print(f"tiles covered: {covered}/{len(X)} ({covered / len(X) * 100:.1f}%)")
    if unmatched:
        print(f"tiles matching no known rune: {unmatched} (possible new runes)")
    missing = [k for k in range(1, len(entries) + 1) if k not in named]
    if missing:
        print(f"unnamed clusters: {missing}")
    print(f"wrote {(BANK / 'runes.npz').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
