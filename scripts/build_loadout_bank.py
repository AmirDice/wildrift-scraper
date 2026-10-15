"""Build the item and rune template banks for the LOADOUT panel.

The catalogue art matches a loadout icon about half the time: 17 of 33 on
the benchmark capture, failing on SCORE rather than on ties, which is the
signature of art that genuinely differs rather than of a gate set too
tight. The game draws its own icons at its own zoom on its own
backgrounds, and no amount of threshold tuning closes that. So the bank
is built from the panel's own pixels.

NAMING IS NOT INFERRED. An earlier version tried to name clusters by
catalogue votes and got most of them wrong, including icons whose colour
was nothing like the guess. The names now come from
data/loadout_icon_labels.json, where the owner named 202 groups by hand
on 2026-10-12, covering 97.7% of harvested item tiles and 99.9% of rune
tiles.

AND THE LABELS ARE KEYED TO PICTURES, NOT NUMBERS. Each label points at
a reference tile in data/icon_bank/loadout_labelled.npz -- the exact
image the owner was shown. This file never has to reproduce the
clustering that produced those groups, which is the whole point: the
last bank was lost when a two-pixel change to the crop moved 430
clusters to 406 and slid 47 labels silently onto their neighbours.

RUN scripts/recut_loadout_refs.py AFTER ANY GEOMETRY CHANGE, and before
this. A reference and a live tile have to be cut by the same rule.
When they were not, Font of Life scored 0.524 against its own reference
-- it is a featureless green glow, so a few pixels of framing move it
further than they move an icon with structure -- the 0.55 gate refused
all 89 of its tiles, the name never entered the bank, and every Font of
Life on the ladder would have read as Triumph. Nothing warned: the name
simply was not there.

    python -m scripts.build_loadout_bank --dry-run      # what it would learn
    python -m scripts.build_loadout_bank                # write both banks
    python -m scripts.build_loadout_bank --kind runes   # just one
    python -m scripts.build_loadout_bank --holdout      # score it honestly

Templates are written to data/icon_bank/loadout_items.npz and
loadout_runes.npz under "<name>#ld<n>" keys. NOT to items.npz or
runes.npz: those two are what the CN leaderboard extraction matches build
popups against, that path works, and nothing here should be able to
re-tune it. icon_match merges each pair into the "loadout_items" and
"loadout_runes" kinds.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import loadouts as L  # noqa: E402
from src import icon_match  # noqa: E402

CAPTURES = ROOT / "data" / "captures_loadouts"
BANKS = ROOT / "data" / "icon_bank"
LABELS = ROOT / "data" / "loadout_icon_labels.json"
REFERENCE = BANKS / "loadout_labelled.npz"

#: Which tabs feed which bank. Boots are items: the panel draws a
#: second-tier boot at exactly the item size, and they share a catalogue.
KINDS = {
    "items": {"tabs": ("equip", "boots"), "bank": BANKS / "loadout_items.npz",
              "circular": False, "match": "loadout_items"},
    "runes": {"tabs": ("runes",), "bank": BANKS / "loadout_runes.npz",
              # Runes are drawn as circles inside a tree-coloured ring, and
              # the matcher scores them through a circular window for that
              # reason. Everything here has to use the same window or it
              # compares ring colour, which is the rune TREE, not the rune.
              "circular": True, "match": "loadout_runes"},
}

#: A harvested tile joins a reference's name above this correlation. The
#: references were cut at a deliberately tight clustering threshold, so a
#: tile that is the same artwork scores far above this and the gate is
#: there to reject the genuinely unseen, not to arbitrate between names.
ASSIGN = 0.55
#: Within one name, looks closer than this are the same look and average
#: together into one template.
LOOK = 0.93
#: Templates kept per name, biggest look first. More is not better: every
#: template is another chance for an unrelated icon to find a friendly
#: angle, and the tail looks are near-duplicates of the head.
PER_NAME = 4
#: A look needs this many tiles to become a template of its own.
MIN_LOOK = 3


# ----------------------------------------------------------------- harvest --
def harvest(kind: str, limit: int = 0):
    """[(tile, source)] for every icon of this kind on disk.

    Geometry comes from src.loadouts: the panel's flat grey background is
    what says where an icon starts and ends, voted across a whole frame so
    one dark rune cannot hide its own column. A frame whose column count
    disagrees with the tab is skipped rather than cut in the wrong places --
    that is how the no-data illustration gets refused.
    """
    tabs = KINDS[kind]["tabs"]
    out = []
    sessions = sorted(d for d in CAPTURES.iterdir() if d.is_dir())
    if limit:
        sessions = sessions[:limit]
    for n, session in enumerate(sessions, 1):
        for frame in sorted(session.glob("*.png")):
            tab = frame.stem.split("_")[0]
            if tab not in tabs:
                continue
            image = cv2.imread(str(frame))
            if image is None:
                continue
            rows = L.find_rows(image)
            if not rows:
                continue
            geom = L.measure_icons(image, rows, L.TABS[tab]["icons"])
            if geom is None:
                continue
            for r, row in enumerate(rows, 1):
                for i, tile in enumerate(geom.tiles(image, row)):
                    if tile is None or tile.size == 0:
                        continue
                    out.append((tile, f"{session.name}/{frame.stem} r{r} s{i}"))
        if n % 40 == 0:
            print(f"  {n}/{len(sessions)} sessions, {len(out)} tiles",
                  flush=True)
    return out


# -------------------------------------------------------------- references --
def references(kind: str):
    """(names, vectors) for the owner's labelled tiles of this kind."""
    doc = json.loads(LABELS.read_text(encoding="utf-8"))
    labels = doc["labels"]
    names, vecs = [], []
    with np.load(REFERENCE) as z:
        for key in z.files:
            if not key.startswith(kind + "-") or key not in labels:
                continue
            names.append(labels[key])
            vecs.append(icon_match._norm_tile(z[key]))
    return names, vecs


def _unit(tile: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """One tile as three unit vectors, one per channel.

    icon_match._score is a weighted, mean-centred correlation per channel,
    averaged. Centre and normalise once here and that score becomes a plain
    dot product, which turns the 1.4 million comparisons this file makes
    into a handful of matrix multiplies. The arithmetic is the same -- the
    assertion in main() checks it against _score itself rather than trusting
    that claim.
    """
    denom = weights.sum()
    out = np.empty((3, weights.size), np.float32)
    for ch in range(3):
        x = tile[:, :, ch]
        xd = (x - (x * weights).sum() / denom) * weights
        n = float(np.sqrt((xd ** 2).sum()))
        out[ch] = (xd / n if n > 1e-6 else xd).ravel()
    return out


def assign(tiles, names, refs, weights):
    """name -> [tile index], plus the indices nothing claimed."""
    bank = np.stack([_unit(r, weights) for r in refs])       # (R, 3, P)
    bank = np.ascontiguousarray(bank.transpose(1, 0, 2))     # (3, R, P)
    taken: dict[str, list[int]] = defaultdict(list)
    loose: list[int] = []
    for i, (tile, _src) in enumerate(tiles):
        u = _unit(icon_match._norm_tile(tile), weights)
        scores = sum(bank[ch] @ u[ch] for ch in range(3)) / 3.0
        j = int(scores.argmax())
        if float(scores[j]) >= ASSIGN:
            taken[names[j]].append(i)
        else:
            loose.append(i)
        if (i + 1) % 4000 == 0:
            print(f"  assigned {i + 1}/{len(tiles)}", flush=True)
    return taken, loose


# ---------------------------------------------------------------- templates --
def looks(vecs, weights):
    """Group one name's tiles into distinct looks, biggest first."""
    units = [_unit(v, weights) for v in vecs]
    groups: list[list[int]] = []
    heads: list[np.ndarray] = []
    for i, u in enumerate(units):
        for j, head in enumerate(heads):
            if float(sum((head[ch] * u[ch]).sum() for ch in range(3))) / 3.0 >= LOOK:
                groups[j].append(i)
                break
        else:
            heads.append(u)
            groups.append([i])
    order = sorted(range(len(groups)), key=lambda j: len(groups[j]),
                   reverse=True)
    return [groups[j] for j in order]


def build(kind: str, tiles, taken, weights, hold: float = 0.0):
    """{'<name>#ld<n>': template}, plus the tile indices held back.

    `hold` keeps that share of each look out of the averaging so there is
    something honest left to score the result on. Zero by default: a bank
    built for use should use everything it has.
    """
    bank, report, held = {}, [], []
    for name in sorted(taken):
        idx = taken[name]
        vecs = [icon_match._norm_tile(tiles[i][0]) for i in idx]
        kept = 0
        for group in looks(vecs, weights):
            if hold and len(group) >= 4:
                cut = max(1, int(len(group) * hold))
                held.extend((name, idx[i]) for i in group[:cut])
                group = group[cut:]
            if kept and len(group) < MIN_LOOK:
                break                 # the tail is noise, not another look
            if kept >= PER_NAME:
                break
            # Average the look rather than pick a member. The panel
            # re-renders the same icon with slightly different compression
            # every frame, and the mean of forty of them is cleaner than any
            # one of them.
            bank[f"{name}#ld{kept}"] = np.mean([vecs[i] for i in group],
                                               axis=0).astype(np.float32)
            kept += 1
        report.append((name, len(idx), kept))
    return bank, report, held


# ---------------------------------------------------------------- holdout --
def holdout(kind: str, tiles, taken, bank):
    """Score the bank on tiles it was NOT built from.

    READ THE NUMBER NARROWLY. Every tile here was given its name by the
    same nearest-reference step that chose the templates, so this measures
    whether the bank GENERALISES from the frames it was averaged over to
    other frames of the same art. It does not independently verify the
    name: that came from the owner labelling the reference tile, and
    nothing here can re-check it.

    The first version of this reported 100.0% and meant nothing at all,
    because --holdout ran after build() had averaged every assigned tile
    into its template, so the test tile was literally part of the thing it
    was scored against. build_split() now keeps a share of each look out of
    the averaging, and those are the tiles scored here.
    """
    icon_match.templates.cache_clear()
    hits = misses = refused = 0
    confusions: dict[tuple[str, str], int] = defaultdict(int)
    step = max(1, len(taken) // 2000)
    for name, i in taken[::step]:
        got, _s, _g, _r = icon_match.match_slot(tiles[i][0],
                                                KINDS[kind]["match"])
        if got == "?":
            refused += 1
        elif got == name:
            hits += 1
        else:
            misses += 1
            confusions[(name, got)] += 1
    total = hits + misses + refused
    return hits, misses, refused, total, confusions


# -------------------------------------------------------------------- main --
def run(kind: str, args) -> int:
    cfg = KINDS[kind]
    print(f"\n=== {kind} ===", flush=True)
    names, refs = references(kind)
    print(f"{len(names)} labelled references, "
          f"{len(set(names))} distinct names", flush=True)

    tiles = harvest(kind, args.limit)
    print(f"{len(tiles)} tiles harvested", flush=True)
    if not tiles:
        print("nothing to build from")
        return 1

    weights = icon_match._weights(True, cfg["circular"])
    taken, loose = assign(tiles, names, refs, weights)
    claimed = sum(len(v) for v in taken.values())
    print(f"{claimed}/{len(tiles)} tiles named ({100 * claimed / len(tiles):.1f}%), "
          f"{len(loose)} unclaimed", flush=True)

    # A --holdout run builds a DELIBERATELY WEAKER bank, so that there is
    # something left to score it on. It must not be the bank that ships.
    bank, report, held = build(kind, tiles, taken, weights,
                               hold=0.35 if args.holdout else 0.0)
    thin = [(n, c, k) for n, c, k in report if k == 0]
    print(f"{len(bank)} templates for {len({k.split('#')[0] for k in bank})} names")
    if thin:
        print(f"  {len(thin)} names with no template: "
              + ", ".join(n for n, _c, _k in thin[:8]))
    if args.verbose:
        for name, count, kept in sorted(report, key=lambda r: -r[1]):
            print(f"    {name:34s} {count:5d} tiles -> {kept} templates")

    if args.dry_run:
        print(f"dry run: would write {cfg['bank'].name}")
        return 0

    np.savez_compressed(cfg["bank"], **bank)
    icon_match.templates.cache_clear()
    print(f"wrote {cfg['bank'].name}: {len(bank)} templates, "
          f"{cfg['bank'].stat().st_size // 1024} KB")

    if args.holdout:
        hits, misses, refused, total, conf = holdout(kind, tiles, held, bank)
        print(f"held-out: {hits}/{total} correct "
              f"({100 * hits / max(1, total):.1f}%), "
              f"{misses} wrong, {refused} refused "
              f"-- on a bank built WITHOUT these tiles, so re-run without "
              f"--holdout before shipping it")
        for (want, got), n in sorted(conf.items(), key=lambda p: -p[1])[:8]:
            print(f"    {n:4d}x  {want}  read as  {got}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=sorted(KINDS), action="append",
                    help="build only this bank (repeatable)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what it would learn, write nothing")
    ap.add_argument("--holdout", action="store_true",
                    help="score the new bank on tiles it was not built from")
    ap.add_argument("--limit", type=int, default=0,
                    help="use only the first N capture sessions")
    ap.add_argument("--verbose", action="store_true",
                    help="list every name and its template count")
    args = ap.parse_args(argv)

    if not LABELS.exists() or not REFERENCE.exists():
        print(f"missing {LABELS.name} or {REFERENCE.name}; "
              f"nothing can be named without them")
        return 2

    # _unit claims to reproduce icon_match._score exactly. Check it, on real
    # templates, before 25,000 tiles are filed by it.
    probe = icon_match._weights(True, True)
    bank = list(icon_match.templates()["runes"].values())[:6]
    for a in bank[:2]:
        for b in bank:
            ua, ub = _unit(a, probe), _unit(b, probe)
            fast = float(sum((ua[c] * ub[c]).sum() for c in range(3))) / 3.0
            slow = icon_match._score(a, probe, b)
            assert abs(fast - slow) < 1e-4, (fast, slow)

    rc = 0
    for kind in (args.kind or sorted(KINDS)):
        rc |= run(kind, args)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
