"""Contact sheets for checking the item and rune template matching by eye.

    python -m scripts.verify_icon_bank

Writes into data/verify/:

  runes_labels.png      every rune template the matcher owns, beside the
                        catalogue art of the name it is filed under. Two
                        pictures of the same symbol means the label is right.
                        This is where wrong names have come from before: the
                        rune bank is built from clusters of captured tiles that
                        are named BY HAND, and a re-cluster once renumbered the
                        naming sheet under the labels.
  rune_clusters.png     the medoid tile of each frozen cluster -- actual game
                        pixels -- with its owner label and what the matcher
                        says when handed that tile. A disagreement here is a
                        real fault, not a judgement call.
  items_labels_1.png    the item templates, which are the site's own catalogue
  items_labels_2.png    art, beside the name they are filed under. A wrong
                        `icon` in data/items.json mislabels that item in every
                        scan, so it is worth an eye even though nothing was
                        hand-named.
  risky.png             every template whose nearest rival is close enough to
                        matter, drawn side by side with the numbers.

And prints the one thing a picture cannot show: for each template, whether the
matcher still picks it when handed a PERFECT copy of itself, and by how much it
beats its runner-up. A template that cannot win against its own bank can never
be read off a capture either; one that wins by less than MIN_GAP resolves to
"?" even on a flawless frame.

What this does NOT verify: the actual EU build popups, which were cleared at
the owner's request on 2026-09-17 (frames deleted, CSVs kept). Verifying a
scanned build against the screen it came from needs a fresh capture run.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.icon_match import MIN_GAP, MIN_SCORE, N, _norm_tile, _score, _weights, templates  # noqa: E402

PUBLIC = ROOT / "web-next" / "public"
OUT = ROOT / "data" / "verify"
CLUSTERS = ROOT / "data" / "icon_bank" / "rune_clusters.npz"
LABELS = ROOT / "data" / "rune_cluster_labels.json"
RUNE_ICONS = ROOT / "web-next" / "src" / "data" / "rune_icons.json"

TILE = 72                      # how big each icon is drawn
PAD = 10
BG = (16, 20, 30)
INK = (232, 236, 244)
DIM = (150, 158, 175)
BAD = (255, 120, 120)
OK = (130, 220, 160)
WARN = (250, 200, 110)


def font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


F = font(15)
FS = font(13)
FH = font(19)


def from_bank(arr: np.ndarray) -> Image.Image:
    """A bank template (float32 BGR) as a picture."""
    a = np.clip(arr, 0, 255).astype(np.uint8)[:, :, ::-1]
    return Image.fromarray(a).resize((TILE, TILE), Image.LANCZOS)


def from_art(rel: str) -> Image.Image | None:
    """Catalogue art, flattened onto the popup's dark panel like the matcher
    flattens it, so the two pictures are comparable."""
    p = PUBLIC / rel.lstrip("/")
    if not rel or not p.exists():
        return None
    im = Image.open(p).convert("RGBA")
    flat = Image.new("RGBA", im.size, (20, 20, 20, 255))
    flat.alpha_composite(im)
    return flat.convert("RGB").resize((TILE, TILE), Image.LANCZOS)


def grid(cells: list[tuple[list[Image.Image | None], list[tuple[str, tuple[int, int, int]]]]],
         cols: int, title: str, cell_w: int) -> Image.Image:
    """Lay out cells of [pictures] + [lines of text] in a grid."""
    pics = max(len(c[0]) for c in cells)
    lines = max(len(c[1]) for c in cells)
    cell_h = max(TILE, 4 + lines * 19) + PAD
    rows = (len(cells) + cols - 1) // cols
    W = PAD + cols * (cell_w + PAD)
    H = 52 + rows * cell_h + PAD
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    d.text((PAD, 16), title, font=FH, fill=INK)
    for i, (images, text) in enumerate(cells):
        cx = PAD + (i % cols) * (cell_w + PAD)
        cy = 52 + (i // cols) * cell_h
        x = cx
        for pic in images:
            if pic is None:
                d.rectangle([x, cy, x + TILE, cy + TILE], outline=(60, 66, 82))
                d.text((x + 18, cy + TILE // 2 - 8), "none", font=FS, fill=DIM)
            else:
                im.paste(pic, (x, cy))
            x += TILE + 4
        ty = cy + 2
        for s, colour in text:
            d.text((x + 6, ty), s, font=F if colour == INK else FS, fill=colour)
            ty += 19
        _ = pics
    return im


def ranked(tile: np.ndarray, kind: str) -> list[tuple[float, str]]:
    """Every candidate for one tile, best first, folded to base names."""
    w = _weights(True, kind == "runes")
    t = _norm_tile(tile) if tile.shape[:2] != (N, N) else tile.astype(np.float32)
    best: dict[str, float] = {}
    for name, tpl in templates()[kind].items():
        base = name.split("#")[0]
        s = _score(t, w, tpl)
        if s > best.get(base, -9.0):
            best[base] = s
    return sorted(((s, n) for n, s in best.items()), reverse=True)


def self_test(kind: str) -> list[dict]:
    """Hand each template back to the matcher as a perfect capture."""
    rows = []
    for name, tpl in sorted(templates()[kind].items()):
        base = name.split("#")[0]
        r = ranked(tpl, kind)
        (s1, n1) = r[0]
        (s2, n2) = r[1] if len(r) > 1 else (0.0, "")
        rows.append({
            "name": name, "base": base, "winner": n1, "score": s1,
            "gap": s1 - s2, "runner_up": n2, "runner_score": s2,
            "wrong": n1 != base, "unresolvable": (s1 - s2) < MIN_GAP or s1 < MIN_SCORE,
        })
    return rows


def rune_label_sheet() -> Image.Image:
    icons = json.loads(RUNE_ICONS.read_text(encoding="utf-8"))
    cells = []
    for name, tpl in sorted(templates()["runes"].items()):
        art = from_art(icons.get(name, ""))
        note = [(name, INK)]
        if art is None:
            note.append(("no catalogue art under this name", BAD))
        cells.append(([from_bank(tpl), art], note))
    return grid(cells, 3, "RUNES: the matcher's template (left) vs the catalogue art it is named after (right)."
                          "  Same symbol = the label is right.", 3 * TILE + 190)


def cluster_sheet() -> Image.Image | None:
    if not CLUSTERS.exists():
        return None
    z = np.load(CLUSTERS)
    art, sizes, guesses = z["art"], z["sizes"], z["guesses"]
    z.close()
    labels = json.loads(LABELS.read_text(encoding="utf-8"))["labels"]
    cells = []
    for i in range(len(art)):
        owner = labels.get(str(i + 1), "")
        tile = art[i]
        verdict = ranked(tile, "runes")
        (s1, n1) = verdict[0]
        s2 = verdict[1][0] if len(verdict) > 1 else 0.0
        pic = Image.fromarray(tile[:, :, ::-1]).resize((TILE, TILE), Image.LANCZOS)
        agree = owner and n1 == owner
        text = [(f"{i + 1}. {owner or '(unlabelled)'}", INK)]
        text.append((
            f"read as {n1}  {s1:.3f}  gap {s1 - s2:.3f}",
            OK if agree else BAD,
        ))
        text.append((f"{int(sizes[i])} tiles · auto guess {guesses[i]}", DIM))
        cells.append(([pic], text))
    return grid(cells, 3, "RUNE CLUSTERS: real game pixels, the owner's label, and what the matcher reads."
                          "  Red = the matcher disagrees with the label.", TILE + 300)


def item_sheets() -> list[Image.Image]:
    names = sorted(templates()["items"].items())
    items = {it["name"]: it.get("icon", "") for it in json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}
    cells = []
    for name, tpl in names:
        base = name.split("#")[0]
        harvested = "#" in name
        text = [(base, INK)]
        if harvested:
            text.append(("harvested from a capture", WARN))
        elif base not in items:
            text.append(("not in items.json", BAD))
        cells.append(([from_bank(tpl)], text))
    half = (len(cells) + 1) // 2
    return [
        grid(cells[:half], 4, "ITEMS 1/2: every template the matcher owns, under the name it is filed as.", TILE + 230),
        grid(cells[half:], 4, "ITEMS 2/2: every template the matcher owns, under the name it is filed as.", TILE + 230),
    ]


def risky_sheet(rows: dict[str, list[dict]]) -> Image.Image:
    icons = json.loads(RUNE_ICONS.read_text(encoding="utf-8"))
    items = {it["name"]: it.get("icon", "") for it in json.loads((ROOT / "data" / "items.json").read_text(encoding="utf-8"))}
    cells = []
    for kind, rs in rows.items():
        risky = sorted((r for r in rs if r["wrong"] or r["gap"] < 0.15), key=lambda r: r["gap"])
        for r in risky:
            left = from_bank(templates()[kind][r["name"]])
            rival = templates()[kind].get(r["runner_up"]) or templates()[kind].get(r["runner_up"] + "#1")
            right = from_bank(rival) if rival is not None else from_art(
                (icons if kind == "runes" else items).get(r["runner_up"], ""))
            verdict = BAD if r["wrong"] else (WARN if r["gap"] < MIN_GAP else DIM)
            cells.append(([left, right], [
                (f"{r['base']}", INK),
                (f"vs {r['runner_up']}", DIM),
                (f"self {r['score']:.3f} · rival {r['runner_score']:.3f} · gap {r['gap']:.3f}", verdict),
            ]))
    if not cells:
        cells = [([None], [("nothing within 0.15 of a rival", OK)])]
    return grid(cells, 2, f"RISKY PAIRS: a perfect copy of the left icon scores this close to the right one."
                          f"  Under {MIN_GAP} (the gap gate) the matcher answers \"?\" instead of guessing.",
                2 * TILE + 320)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = {"items": self_test("items"), "runes": self_test("runes")}

    for kind, rs in rows.items():
        wrong = [r for r in rs if r["wrong"]]
        unres = [r for r in rs if r["unresolvable"] and not r["wrong"]]
        print(f"\n{kind}: {len(rs)} templates")
        print(f"  win against their own bank: {len(rs) - len(wrong)}/{len(rs)}")
        for r in wrong:
            print(f"  WRONG  {r['name']:<34} read as {r['winner']} ({r['score']:.3f})")
        print(f"  would resolve on a perfect frame: {len(rs) - len(wrong) - len(unres)}/{len(rs)}")
        for r in unres:
            print(f"  TIGHT  {r['name']:<34} gap {r['gap']:.3f} to {r['runner_up']}")
        tight = sorted(rs, key=lambda r: r["gap"])[:5]
        print("  closest pairs: " + ", ".join(f"{r['base']}/{r['runner_up']} {r['gap']:.3f}" for r in tight))

    sheets = {
        "runes_labels.png": rune_label_sheet(),
        "rune_clusters.png": cluster_sheet(),
        "risky.png": risky_sheet(rows),
    }
    for i, sheet in enumerate(item_sheets(), start=1):
        sheets[f"items_labels_{i}.png"] = sheet
    for name, im in sheets.items():
        if im is None:
            continue
        im.save(OUT / name)
        print(f"wrote {OUT / name}  {im.size[0]}x{im.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
