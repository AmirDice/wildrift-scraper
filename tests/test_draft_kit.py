"""The authored capability values, checked against facts we already derived.

data/champion_draft_kit.json is model-generated. champion_identity.json is too,
and 97 of 139 of those cards recommended items the ladder never builds, because
nothing mechanical stood between the model and the file.

The generator lints every card before accepting it. This runs the same lint
over what is actually COMMITTED, so a hand edit or a regeneration cannot put a
contradiction into the repo without a test going red. It deliberately checks
only claims that would be factually wrong -- a frontline number on a marksman,
disruption on a champion with no measured crowd control -- and leaves the
judgement calls alone, because judgement is what the file is for.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.generate_draft_kit import AXES, lint  # noqa: E402

ROSTER = json.loads((ROOT / "web-next" / "src" / "data" / "roster.json")
                    .read_text(encoding="utf-8"))
KIT = json.loads((ROOT / "data" / "champion_draft_kit.json")
                 .read_text(encoding="utf-8"))["champions"]


def test_every_card_survives_its_own_lint():
    bad = []
    for name, card in KIT.items():
        row = ROSTER.get(name)
        if not row:
            continue
        problems = lint(name, card, row)
        if problems:
            bad.append("%s: %s" % (name, "; ".join(problems)))
    assert not bad, "\n".join(bad)


def test_every_card_is_a_complete_vector():
    # A partial card is legal by design -- the merge is per field -- but a
    # generated one should be whole, and a missing axis silently falls back to
    # the derived value it was authored to replace.
    for name, card in KIT.items():
        missing = [a for a in AXES if a not in card]
        assert not missing, "%s missing %s" % (name, ", ".join(missing))


def test_the_roster_carries_them():
    for name, card in KIT.items():
        row = ROSTER.get(name)
        if row is not None:
            assert row.get("draftKit") == card, name


def test_champions_are_actually_distinguishable():
    """The whole reason this file exists.

    Derived kits put Galio, Alistar and Rell on the identical vector -- all
    three being "a Tank that protects allies with three lockdown abilities" --
    and the ranking then fell through to ladder strength and answered every
    draft calling for that archetype with whoever was strongest that patch.
    """
    vectors = {json.dumps(c, sort_keys=True) for c in KIT.values()}
    assert len(vectors) > len(KIT) * 0.9, (
        "%d distinct vectors across %d champions -- too many ties"
        % (len(vectors), len(KIT)))
    for a, b in (("Alistar", "Galio"), ("Galio", "Rell"), ("Alistar", "Rell"),
                 ("Leona", "Alistar"), ("Lulu", "Janna")):
        assert KIT[a] != KIT[b], "%s and %s rate identically" % (a, b)
