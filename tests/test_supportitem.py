"""The free support item: mandatory, first, and support-only.

The bug these cover: the advisor had no concept of the support item at all, so
every support build it produced opened with a 3000g legendary and skipped the
0g item that pays for the rest of the game.
"""
from __future__ import annotations

import pytest

from web.advisor import itemmeta, profiles, supportitem

FOUR = ["liandrys-torment", "rabadons-deathcap", "void-staff", "banshees-veil"]
FIVE = ["luden-tempest", *FOUR]


class TestSupportBuilds:
    def test_a_support_build_without_one_gains_it_in_first_slot(self):
        items, changed = supportitem.enforce(FIVE, "Support", "Enchanter")
        assert changed
        assert items[0] in supportitem.SUPPORT_ITEMS
        assert len(items) == 5

    def test_the_model_choice_is_kept_when_it_made_one(self):
        picked = [supportitem.TANKY, *FOUR]
        items, changed = supportitem.enforce(picked, "Support", "Enchanter")
        assert items == picked
        assert not changed

    def test_a_support_item_bought_late_is_moved_to_first(self):
        """Correct item, wrong timing: it is the first purchase or it is nothing."""
        items, _ = supportitem.enforce([*FOUR, supportitem.DAMAGE], "Support", "Enchanter")
        assert items[0] == supportitem.DAMAGE
        assert len(items) == 5

    def test_two_support_items_collapse_to_one(self):
        items, _ = supportitem.enforce(
            [supportitem.TANKY, supportitem.DAMAGE, *FOUR[:3]], "Support", "Tank")
        assert [s for s in items if s in supportitem.SUPPORT_ITEMS] == [supportitem.TANKY]

    def test_the_build_keeps_five_items(self):
        """Four real items plus the support item, which is what fits."""
        for cls in ("Enchanter", "Tank", "Mage", "Marksman"):
            items, _ = supportitem.enforce(FIVE, "Support", cls)
            assert len(items) == 5, cls
            assert len(set(items)) == 5, cls

    def test_the_role_check_is_not_case_sensitive(self):
        items, _ = supportitem.enforce(FIVE, "support", "Enchanter")
        assert items[0] in supportitem.SUPPORT_ITEMS


class TestWhichSupportItem:
    @pytest.mark.parametrize("champion_class", ["Tank", "Bruiser", "Fighter"])
    def test_durable_supports_default_to_the_health_one(self, champion_class):
        assert supportitem.default_for(champion_class) == supportitem.TANKY

    @pytest.mark.parametrize("champion_class", ["Enchanter", "Mage", "Marksman", ""])
    def test_everyone_else_defaults_to_the_adaptive_damage_one(self, champion_class):
        assert supportitem.default_for(champion_class) == supportitem.DAMAGE


class TestNonSupportBuilds:
    @pytest.mark.parametrize("role", ["Mid", "Jungle", "Baron", "Dragon", ""])
    def test_a_support_item_is_stripped_outside_the_role(self, role):
        items, changed = supportitem.enforce([supportitem.DAMAGE, *FOUR], role, "Mage")
        assert not [s for s in items if s in supportitem.SUPPORT_ITEMS]
        assert changed

    def test_an_ordinary_build_is_left_exactly_alone(self):
        items, changed = supportitem.enforce(FIVE, "Mid", "Mage")
        assert items == FIVE
        assert not changed


class TestThePoolMatchesTheRule:
    """The strip above is a safety net; the pool is the real defence.

    Leaving the support items visible to a solo laner and removing them
    afterwards would hand back a four-item build, so they must not be offered
    outside the role in the first place.
    """

    def _pool(self, champion: str, role: str) -> list[str]:
        record = profiles.CHAMPIONS.get(champion) or {}
        kept, _ = itemmeta.filter_candidates(
            record, profiles.combat_profile(champion),
            profiles.scaling_profile(champion), role=role)
        return kept

    def test_support_builds_can_see_both_support_items(self):
        pool = self._pool("Lulu", "Support")
        assert supportitem.SUPPORT_ITEMS <= set(pool)

    def test_a_mid_laner_is_never_offered_one(self):
        pool = self._pool("Lux", "Mid")
        assert not (supportitem.SUPPORT_ITEMS & set(pool))

    def test_the_same_champion_played_support_does_see_them(self):
        """The user's case: generating a support build for an off-role pick."""
        assert supportitem.SUPPORT_ITEMS <= set(self._pool("Lux", "Support"))
        assert not (supportitem.SUPPORT_ITEMS & set(self._pool("Lux", "Mid")))
