"""The scraper's champion list and the site's roster must not drift apart.

src/champions.py is hand-maintained ("Extend as new champions release") and is
the ONLY thing that turns an OCR'd label into a champion. A name missing from
it cannot be matched, so the carousel taps that champion's row, fails to
confirm the label, backs out, and after two attempts marks the champion as
done. It never scrapes and it never says why.

Yunara shipped and was not added. Her label OCR'd perfectly -- "YUNARA", clean,
fourteen times across two overnight runs -- and every read was thrown away by a
dictionary lookup that had no entry for her. Fourteen debug frames, two wasted
runs, and nothing in the output naming the cause.

The site roster (data/champions_wr.json) is derived from scraped data, so it is
the list that grows on its own. This test makes it the authority for what the
matcher has to know.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from src.champions import CHAMPIONS, match  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE_ROSTER = json.loads((ROOT / "data" / "champions_wr.json").read_text(encoding="utf-8"))
SITE_NAMES = sorted(SITE_ROSTER if isinstance(SITE_ROSTER, dict)
                    else {c["name"] for c in SITE_ROSTER})


def test_every_tracked_champion_is_known_to_the_matcher():
    missing = [n for n in SITE_NAMES if n not in set(CHAMPIONS)]
    assert not missing, (
        f"{missing} are on the site roster but absent from src/champions.py, so the "
        f"scraper cannot identify them on screen. Add them to CHAMPIONS.")


def test_every_tracked_champion_matches_from_its_own_name():
    """Membership is not enough: the name has to survive normalisation and the
    token-span search that read_champion_name actually uses. 'Nunu & Willump'
    and 'Dr. Mundo' are the ones that make this more than a set check."""
    for name in SITE_NAMES:
        assert match(name.split()) == name, (
            f"{name!r} is in CHAMPIONS but does not match itself; the matcher would "
            f"reject a PERFECT OCR read of this champion's label")


def test_the_matcher_may_know_names_the_site_does_not():
    """The reverse direction is deliberately NOT an error.

    The matcher carries champions Wild Rift has released but the site does not
    track yet. Knowing a name it never sees costs nothing; not knowing one it
    does see costs a champion.
    """
    extra = set(CHAMPIONS) - set(SITE_NAMES)
    assert "Yunara" not in extra, "Yunara should now be on both lists"


def test_no_duplicate_entries():
    dupes = {n for n in CHAMPIONS if CHAMPIONS.count(n) > 1}
    assert not dupes, f"duplicated in CHAMPIONS: {sorted(dupes)}"
