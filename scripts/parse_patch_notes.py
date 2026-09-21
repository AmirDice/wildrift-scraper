"""Turn an official Wild Rift patch-notes page into structured JSON.

WHY

    7.3 is the largest patch this site has had to absorb: 32 champions with
    ability or base-stat edits, a 51-champion durability appendix, a
    140-champion attack-speed appendix, ten new items, three removals and
    roughly forty item edits. Hand-typing that into an apply script is where
    transcription errors come from, and the previous patches proved it (a
    dropped tenth on Malphite's armour, a cooldown pair read off the wrong
    rank).

    So the notes are parsed once, mechanically, and every later step reads the
    parse. What the apply scripts then assert is OUR data, not the transcript:
    the transcript is the source of truth for what the patch says, our asserts
    are the check that we were where the patch expected us to be.

STRUCTURE OF THE PAGE

    Riot's page is two kinds of blade, in document order:

    * `CharacterChanges` -- one container per champion
      (`character-changes-<NAME>`), each holding "Base Stats" and one block per
      ability, every block a bullet list.
    * `ArticleRichTextBlade` -- free rich text with h2..h6 headings and bullet
      lists. Items, runes, the battlefield and both appendices live here, so a
      bullet only means something together with the headings above it. Each
      block therefore carries its full heading `path`.

    Both are emitted as blades in the order they appear, so the JSON can be
    read top to bottom like the article.

USAGE

    python -m scripts.parse_patch_notes --patch 7.3 \
        --url https://wildrift.leagueoflegends.com/en-gb/news/game-updates/wild-rift-patch-notes-7-3/
    python -m scripts.parse_patch_notes --patch 7.3 --html saved.html --out data/patch_notes_7_3.json

    --report prints the counts and the section outline without writing.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; WrTrueMeta/1.0)"}
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def clean(text: str) -> str:
    """Page text as a single line: no non-breaking spaces, no doubled spaces.

    The arrow stays as published (U+2192). Every downstream step splits on it,
    and rewriting it to "->" would make the transcript disagree with the page
    it is a transcript of.
    """
    text = unicodedata.normalize("NFKC", text or "").replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


def champion_blade(container: Tag) -> dict:
    """One champion's changes, plus Riot's rationale where they wrote one.

    The rationale ("Twitch's current kit hasn't been delivering...") sits in a
    `character-changes-summary` div inside the same container, and it is the
    sentence the site's change history should quote for a rework.
    """
    name = clean(container.select_one('[data-testid="character-name"]').get_text())
    summary = container.select_one('[data-testid="character-changes-summary"]')
    blocks: list[dict] = []
    for change in container.select("div.character-change"):
        title = change.select_one('[data-testid="character-ability-title"]')
        lines = [clean(li.get_text()) for li in change.select("li")]
        # A few blocks carry their change as a paragraph instead of a list
        # (Twitch's rewritten Venom Cask is one), and dropping those would lose
        # the whole ability.
        if not lines:
            lines = [clean(p.get_text()) for p in change.select("div.character-change-body p")]
        blocks.append({
            "title": clean(title.get_text()) if title else "",
            "lines": [l for l in lines if l],
        })
    return {
        "kind": "champion",
        "champion": name,
        "summary": clean(summary.get_text()) if summary else "",
        "blocks": blocks,
    }


def rich_blade(section: Tag) -> dict:
    """Free rich text, flattened to heading-addressed blocks.

    Every bullet is kept with the heading path above it, because "Price: 500 →
    400" is only meaningful under "Item Adjustments / Marksman Item Adjustments
    / Dagger". Paragraphs under a heading are kept as `notes`: Riot explains
    the intent there, which is what the change-history summary quotes.
    """
    blocks: list[dict] = []
    stack: list[tuple[int, str]] = []          # (level, title) of the headings above
    current: dict | None = None
    # A name written as a plain paragraph rather than a heading. The
    # attack-speed appendix lists all 140 champions that way ("<p>Taliyah</p>",
    # "<p><i>Base Stats</i></p>", list), and without this every one of those
    # lists would land under whichever heading came last.
    pending: str | None = None

    def start(title: str, level: int, synthetic: bool = False) -> None:
        nonlocal current
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        current = {"level": level, "title": title, "path": [t for _, t in stack], "notes": [], "lines": []}
        if synthetic:
            current["fromParagraph"] = True
        blocks.append(current)

    def sibling_level() -> int:
        """Where a paragraph-named block belongs: beside the previous one when
        that was also paragraph-named (the appendix lists 140 champions in a
        row), otherwise one level under the heading it follows."""
        return current["level"] if current.get("fromParagraph") else current["level"] + 1

    for node in section.select('[data-testid="rich-text-html"]'):
        for el in node.find_all(HEADINGS + ("p", "ul", "ol"), recursive=True):
            # find_all descends, so a <p> inside a <li> would be counted twice.
            if el.find_parent(["li", "ul", "ol"]) is not None:
                continue
            text = clean(el.get_text())
            if not text:
                continue
            if el.name in HEADINGS:
                start(text, int(el.name[1]))
                pending = None
                continue
            if current is None:
                start("", 0)
            if el.name == "p":
                # A short paragraph with no sentence in it is a name: the item
                # passive above its description ("Practice Makes Perfect",
                # "Energized:") or a champion in the appendix. "Base Stats" is
                # the label every block carries, so it names nothing.
                label = text.rstrip(":")
                names = (label.lower() != "base stats" and len(label) <= 60
                         and not text.endswith((".", "!", "?")))
                if pending and not names:
                    # The pending name's body, written as prose rather than a
                    # list -- most item passives are.
                    start(pending, sibling_level(), synthetic=True)
                    pending = None
                    current["lines"].append(text)
                    continue
                current["notes"].append(text)
                if names:
                    pending = label
                continue
            lines = [t for t in (clean(li.get_text()) for li in el.find_all("li", recursive=False)) if t]
            if pending and pending != current["title"]:
                start(pending, sibling_level(), synthetic=True)
                pending = None
            current["lines"].extend(lines)
    return {"kind": "rich", "id": clean(section.get("id") or ""), "blocks": blocks}


def parse(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    blades: list[dict] = []
    for section in soup.find_all("section"):
        kind = section.get("data-testid") or ""
        if kind == "CharacterChanges":
            # The container class, not the testid prefix: the prefix also
            # matches the per-champion `character-changes-summary` block that
            # lives INSIDE a container and has no champion name of its own.
            for container in section.select("div.character-changes-container"):
                blades.append(champion_blade(container))
        elif kind == "ArticleRichTextBlade":
            blade = rich_blade(section)
            if any(b["lines"] or b["notes"] for b in blade["blocks"]):
                blades.append(blade)
    return blades


def outline(blades: list[dict]) -> None:
    champs = [b["champion"] for b in blades if b["kind"] == "champion"]
    print(f"{len(blades)} blades, {len(champs)} champion blocks")
    print("champions:", ", ".join(champs))
    for blade in blades:
        if blade["kind"] != "rich":
            continue
        print(f'\n=== {blade["id"] or "(untitled)"} ===')
        for block in blade["blocks"]:
            if not block["lines"]:
                continue
            print(f'  {"  " * block["level"]}{block["title"]}: {len(block["lines"])} lines')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--patch", required=True, help='e.g. "7.3"')
    ap.add_argument("--url", help="patch notes URL (fetched if --html is not given)")
    ap.add_argument("--html", type=Path, help="a saved copy of the page instead of fetching")
    ap.add_argument("--out", type=Path, help="default: data/patch_notes_<patch>.json")
    ap.add_argument("--report", action="store_true", help="print the outline, write nothing")
    args = ap.parse_args()

    if args.html:
        html = args.html.read_text(encoding="utf-8", errors="replace")
    elif args.url:
        html = requests.get(args.url, headers=HEADERS, timeout=60).text
    else:
        ap.error("one of --url or --html is required")

    blades = parse(html)
    if not blades:
        print("nothing parsed: the page markup has changed")
        return 1

    payload = {
        "patch": args.patch,
        "url": args.url or str(args.html),
        "parsedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "blades": blades,
    }
    if args.report:
        outline(blades)
        return 0
    out = args.out or DATA / f"patch_notes_{args.patch.replace('.', '_')}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    champs = sum(1 for b in blades if b["kind"] == "champion")
    lines = sum(len(x["lines"]) for b in blades for x in b["blocks"])
    print(f"{out.relative_to(ROOT)}: {len(blades)} blades, {champs} champions, {lines} change lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
