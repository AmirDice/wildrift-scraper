"""Hard crowd control, which decides whether tenacity is worth a rune slot.

Reported: a Wukong build took Legend: Tenacity against a team whose only real
lockdown was Sona. The prompt already said tenacity needs three enemies and a
validator already enforced it, so the sentence and the gate were both fine --
the COUNT feeding them was not. The deriving regex tagged 97 of 141 champions,
because it fired on the word "slow", and an average five-stack therefore always
cleared the bar.

These pin the derivation rather than the ranking, in the same spirit as
test_draft_traits: the ranking is tuning and can be argued about, but whether
Pantheon has a stun is a fact.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from web.advisor import hardcc, profiles  # noqa: E402

ROSTER = json.loads((ROOT / "web-next" / "src" / "data" / "roster.json")
                    .read_text(encoding="utf-8"))


def cc(name: str) -> bool:
    record = profiles.CHAMPIONS.get(name) or {}
    return hardcc.has_hard_cc(record.get("abilities"), name)


def depth(name: str) -> int:
    record = profiles.CHAMPIONS.get(name) or {}
    return hardcc.hard_cc_depth(record.get("abilities"), name)


class TestTheFourWaysItWasWrong:
    def test_a_veto_cannot_reach_into_another_ability(self):
        # Pantheon's W stuns. The old filter looked back 90 characters through
        # his abilities CONCATENATED and found "reduced" in the passive's
        # monster-damage clause, which threw the stun away.
        assert cc("Pantheon")

    def test_an_ally_target_does_not_delete_an_enemy_effect(self):
        # Lulu's ultimate enlarges an ALLY and knocks up ENEMIES. A flat veto
        # on the word "ally" lost the knockup.
        assert cc("Lulu")

    def test_the_verb_forms_tooltips_actually_use(self):
        # `knock\\s?up` matched neither "knocks up" nor "Knocks a target and
        # enemies near them backwards", so these four read as harmless.
        for name in ("Wukong", "Fizz", "Jayce", "Ziggs"):
            assert cc(name), name

    def test_an_ability_name_is_not_an_ability(self):
        # Kha'Zix has no fear. He has an ability called "Taste Their Fear",
        # quoted by name inside another ability's text.
        assert not cc("Kha'Zix")


class TestVocabulary:
    def test_sleep_counts(self):
        for name in ("Zoe", "Lillia"):
            assert cc(name), name

    def test_displacement_counts(self):
        # Orianna's "launching nearby enemies", Darius's apprehend.
        for name in ("Orianna", "Darius", "Mordekaiser"):
            assert cc(name), name

    def test_a_travelling_projectile_is_not_displacement(self):
        # Kai'Sa "Launches 6 missiles" and Talon "Tosses daggers" are the verb
        # without a victim; Katarina's dagger spends its time "in the air".
        for name in ("Kai'Sa", "Talon", "Katarina"):
            assert not cc(name), name

    def test_slows_alone_are_not_hard_crowd_control(self):
        # The whole original defect. These have slows and nothing that stops
        # you acting, and tenacity is not the answer to any of them.
        for name in ("Master Yi", "Nasus", "Teemo", "Sivir", "Dr. Mundo"):
            assert not cc(name), name


class TestDepthSeparatesComps:
    def test_one_stun_is_not_three(self):
        # The reported build's whole argument: Sona is real crowd control and
        # is not a reason to spend a rune slot on tenacity.
        assert depth("Sona") < depth("Alistar")
        assert depth("Sona") <= 2

    def test_a_lockdown_comp_reads_far_above_an_ordinary_one(self):
        from web.advisor import threats
        heavy = threats.team_threat_profile(
            ["Alistar", "Leona", "Amumu", "Ashe", "Malphite"])
        light = threats.team_threat_profile(
            ["Sona", "Master Yi", "Gwen", "Nasus", "Akali"])
        assert heavy["hardCcCount"] >= 4
        assert light["hardCcCount"] <= 1
        assert heavy["hardCcDepth"] >= 2 * light["hardCcDepth"]

    def test_the_tenacity_gate_would_block_the_reported_build(self):
        from web.advisor import threats
        profile = threats.team_threat_profile(
            ["Sona", "Master Yi", "Gwen", "Nasus", "Akali"])
        assert profile["hardCcCount"] < 3


class TestTheOverlayGetsTheSameAnswer:
    """The exporter and the advisor read one module now. They used to hold
    copies of the same regex pair, which is how they were free to drift."""

    def test_the_bundle_agrees_with_the_deriver(self):
        for name, row in ROSTER.items():
            tagged = "cc" in (row.get("mechanics") or [])
            assert tagged == cc(name), name

    def test_the_bundle_carries_the_depth(self):
        for name, row in ROSTER.items():
            assert row.get("ccDepth") == depth(name), name
