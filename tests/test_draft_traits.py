"""Kit traits the pick ranker needs, and class alone cannot express.

Reported: against Malphite, Amumu, Lissandra, Ashe and Leona -- five enemies
who all lock you down -- the assistant recommended Hecarim, Pantheon and Diana
ABOVE Olaf, whose ultimate removes every debuff and makes him immune. Olaf
scored with no stated reason at all, because the ranker had no representation
of crowd-control immunity, and none of true damage either, so he registered as
no answer to a team of tanks despite carrying no percent-health damage at all.

These pin the derived traits rather than the ranking, because the ranking is
tuning and the traits are facts.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ROSTER = json.loads((ROOT / "web-next" / "src" / "data" / "roster.json")
                    .read_text(encoding="utf-8"))


def trait(name: str, key: str) -> bool:
    return bool((ROSTER.get(name) or {}).get(key))


class TestCrowdControlImmunity:
    def test_olaf_clears_crowd_control(self):
        assert trait("Olaf", "ccImmune")

    def test_the_other_known_answers_are_found(self):
        for name in ("Sivir", "Master Yi", "Nocturne"):
            assert trait(name, "ccImmune"), name

    def test_it_is_not_confused_by_text_about_the_enemy(self):
        """Darius's ultimate text lists "the target ... becomes untargetable"
        as a case where his RESET FAILS, and Zilean's revives an ally who
        "become[s] untargetable". Both read as self-immunity without a guard
        on who the sentence is about."""
        assert not trait("Darius", "ccImmune")
        assert not trait("Zilean", "ccImmune")

    def test_it_stays_a_short_list(self):
        """A trait most of the roster has cannot rank anything."""
        n = sum(1 for c in ROSTER.values() if c.get("ccImmune"))
        assert 3 <= n <= 20, f"{n} champions marked crowd-control immune"


class TestAntiFrontlineDamage:
    def test_olaf_answers_tanks_through_true_damage(self):
        """He carries no percent-health damage at all, which is why he never
        registered against a team of tanks."""
        assert trait("Olaf", "trueDamage")
        assert not trait("Olaf", "pctHpDamage")

    def test_the_percent_health_carriers_are_still_flagged(self):
        for name in ("Gwen", "Shyvana", "Lillia", "Vayne", "Fiora"):
            assert trait(name, "pctHpDamage"), name

    def test_a_trait_carried_only_by_a_transform_form_still_counts(self):
        """Kayn's percent-health damage lives entirely on Rhaast, and the
        roster excludes forms -- so base Kayn read as no answer to tanks while
        a player drafting Kayn is choosing Rhaast as part of the pick."""
        assert trait("Kayn", "pctHpDamage")


class TestTraitsReachBothCallers:
    def test_the_roster_carries_every_trait_the_ranker_reads(self):
        """The trait bundle was built twice -- once in the draft page, once in
        the report harness -- and the copies drifted. Both now call one builder
        in lib/draft.ts, which reads these keys off every roster row."""
        for key in ("pctHpDamage", "trueDamage", "ccImmune", "mechanics"):
            missing = [n for n, c in ROSTER.items() if key not in c]
            assert not missing, f"{key} missing from {missing[:5]}"
