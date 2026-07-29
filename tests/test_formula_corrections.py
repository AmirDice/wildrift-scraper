"""The formula_corrections.json overlay actually lands, in every consumer.

These corrections fix LLM-extracted `knowledge`/`mechanics` errors that a
re-extraction would regenerate: Graves flagged manaless while paying 65-80
mana per Q, Garen and Mordekaiser labelled resource=mana while having no
resource at all, and asEfficiency stuck at the 0.2 caster floor on kits whose
abilities explicitly count attacks. If a re-extraction (or a refactor of a
loader) drops the overlay, these tests name the exact champion that broke.
"""
import json
from pathlib import Path

from web.advisor import profiles
from web import fight_engine

ROOT = Path(__file__).resolve().parent.parent


def _know(formulas, name):
    return (formulas.get(name) or {}).get("knowledge") or {}


def _mechanic_kinds(formulas, name):
    return [m.get("kind") for m in (formulas.get(name) or {}).get("mechanics") or []]


class TestFactualResourceFixes:
    def test_graves_is_not_manaless(self):
        """He has 390 base mana and per-cast costs; the extraction said none.

        The visible symptom was the prompt telling the model Graves 'has NO
        mana, so mana ... STATS are dead on it', which is simply false.
        """
        assert _know(profiles.FORMULAS, "Graves").get("resource") == "mana"
        assert "noResource" not in _mechanic_kinds(profiles.FORMULAS, "Graves")
        flat = " ".join(profiles.kit_mechanics("Graves"))
        assert "NO mana" not in flat

    def test_garen_and_mordekaiser_are_manaless(self):
        for name in ("Garen", "Mordekaiser"):
            assert _know(profiles.FORMULAS, name).get("resource") == "none", name
            flat = " ".join(profiles.kit_mechanics(name)).lower()
            assert "no mana" in flat, f"{name} lost the manaless statement"

    def test_kennen_keeps_his_true_noresource_mechanic(self):
        """Kennen is energy: 'no mana' is TRUE for him and must survive."""
        assert "noResource" in _mechanic_kinds(profiles.FORMULAS, "Kennen")


class TestAttackSpeedEfficiencyFloorEscapes:
    def test_attack_counting_kits_left_the_caster_floor(self):
        """Twisted Fate's own ability GRANTS attack speed; 0.2 was Annie's value."""
        for name in ("Twisted Fate", "Nilah", "Kennen"):
            eff = _know(profiles.FORMULAS, name).get("asEfficiency")
            assert eff and eff >= 0.7, f"{name} asEfficiency={eff}, back at the floor"

    def test_fight_engine_sees_the_same_values(self):
        """asEfficiency multiplies into attack speed in simulation, so the two
        loaders disagreeing would grade items differently from the prompt."""
        for name in ("Twisted Fate", "Nilah", "Kennen", "Graves"):
            assert (_know(fight_engine.FORMULAS, name)
                    == _know(profiles.FORMULAS, name)), name


class TestFixedAttackSpeedProfiles:
    def test_fixed_attack_speed_kits_stop_rating_attack_speed_high(self):
        """Both carry fixedAttackSpeed, yet the derived profile rated
        attackSpeedValue 'high' -- the same prompt then said attack speed
        converts poorly. The curated override wins."""
        for name in ("Jhin", "Senna"):
            assert profiles.combat_profile(name)["attackSpeedValue"] == "low", name

    def test_jhin_on_hit_is_low_but_senna_stays_high(self):
        """The two axes deliberately differ. Jhin's four-shot magazine gates
        on-hit application, so both axes are low. Senna's per-auto Mist passive
        is genuine on-hit reliance -- every auto matters, buying MORE autos per
        second is what does not work -- so only her attack-speed axis drops."""
        assert profiles.combat_profile("Jhin")["repeatedOnHitReliance"] == "low"
        assert profiles.combat_profile("Senna")["repeatedOnHitReliance"] == "high"


class TestOverlayIntegrity:
    def test_every_entry_names_a_real_champion_and_a_reason(self):
        overlay = json.loads(
            (ROOT / "data" / "formula_corrections.json").read_text(encoding="utf-8"))
        for name, entry in overlay["champions"].items():
            assert name in profiles.FORMULAS, f"unknown champion {name!r}"
            assert entry.get("reason"), f"{name} has no reason"
