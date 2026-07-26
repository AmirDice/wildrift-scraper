"""When each champion arrived in Wild Rift, from the official patch notes.

The balance report wants to say "Vel'Koz has never been changed in the N days
since release", and that sentence is only worth printing if the date behind it
is real. Riot announces every champion in the patch notes -- "making his debut",
"NEW CHAMPIONS", "is landing on the Rift" -- so the date is already sitting in
data/official_patch_history.json; it just was not extracted.

Each entry records the patch, its publish date, and the sentence the match came
from, so any date on the site can be traced back to the note that announced it.

Champions released before the earliest patch in the history simply do not
appear. That is the honest outcome: we do not know their release date, so the
report says "since we started tracking" for them instead of inventing one.

Run:
    python -m scripts.extract_champion_releases
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HISTORY = ROOT / "data" / "official_patch_history.json"
ROSTER = ROOT / "web-next" / "src" / "data" / "roster.json"
OUT = ROOT / "data" / "champion_releases.json"
WEB_OUT = ROOT / "web-next" / "src" / "data" / "champion_releases.json"

# Phrases Riot uses to announce a champion. Kept narrow on purpose: a champion
# merely *mentioned* in a patch is not a champion being released, and a loose
# pattern would date every champion to whenever they were first nerfed.
DEBUT_PATTERNS = [
    r"making (?:his|her|their|its) debut",
    r"is (?:making|about to make) (?:his|her|their|its) (?:debut|entrance)",
    r"is landing on the rift",
    r"(?:joins|has arrived on|arrives on) the rift",
    r"new champions?\b",
    r"is (?:now )?available",
    r"arrives? (?:on|in) (?:the )?wild rift",
    r"introduc(?:e|es|ing) the newest",
    r"newest (?:champion|marksman|mage|assassin|tank|support|fighter|bruiser|enchanter)",
]

# Skin and cosmetic releases mention champions constantly ("Cosmic Sting
# Skarner will be released on July 9"). None of the patterns above match that
# wording, and they must stay that way: a looser rule would date champions to
# whenever they next got a skin.
DEBUT_RE = re.compile("|".join(DEBUT_PATTERNS), re.IGNORECASE)

# How far from the champion's name a debut phrase still counts as being about them.
WINDOW = 220


def normalise(text: str) -> str:
    """Fold the typographic apostrophes Riot uses so Vel'Koz matches Vel’Koz."""
    text = unicodedata.normalize("NFKD", text)
    return text.replace("’", "'").replace("‘", "'")


def patch_text(patch: dict) -> str:
    parts = [patch.get("title") or ""]
    parts.extend(patch.get("textBlocks") or [])
    parts.extend(patch.get("changeLines") or [])
    return normalise(" ".join(str(p) for p in parts))


def main() -> None:
    history = json.loads(HISTORY.read_text(encoding="utf-8"))
    patches = sorted(history["patches"], key=lambda p: p.get("publishedAt") or "")
    champions = sorted(json.loads(ROSTER.read_text(encoding="utf-8")))

    earliest = patches[0].get("publishedAt", "")[:10] if patches else ""
    releases: dict[str, dict] = {}

    for patch in patches:
        text = patch_text(patch)
        lowered = text.lower()
        for champion in champions:
            if champion in releases:
                continue
            name = normalise(champion).lower()
            start = lowered.find(name)
            if start < 0:
                continue
            window = text[max(0, start - WINDOW): start + WINDOW]
            match = DEBUT_RE.search(window)
            if not match:
                continue
            sentence = re.sub(r"\s+", " ", window).strip()
            releases[champion] = {
                "patch": patch.get("patch"),
                "releasedAt": patch.get("publishedAt"),
                "url": patch.get("url"),
                "evidence": sentence[:240],
            }

    payload = {
        "source": "data/official_patch_history.json",
        "note": "Release patch per champion, matched from Riot's own announcement wording. "
                "Champions absent here were released before the patch history begins.",
        "historyStartsAt": earliest,
        "releases": dict(sorted(releases.items())),
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT.write_text(body, encoding="utf-8")
    WEB_OUT.write_text(body, encoding="utf-8")

    print(f"patch history covers {len(patches)} patches from {earliest}")
    print(f"dated {len(releases)} of {len(champions)} champions")
    print(f"wrote {OUT.relative_to(ROOT)} + {WEB_OUT.relative_to(ROOT)}\n")
    for champion in ("Vel'Koz", "Yunara", "Skarner", "Cho'Gath"):
        entry = releases.get(champion)
        print(f"  {champion:10} {entry['patch']:>6}  {entry['releasedAt'][:10]}" if entry
              else f"  {champion:10} (predates the patch history)")


if __name__ == "__main__":
    main()
