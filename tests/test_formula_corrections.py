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
    def test_nilah_left_the_caster_floor(self):
        """A melee Marksman cannot share Annie's attack-speed value.

        Twisted Fate and Kennen deliberately do NOT appear here: their raised
        values were reverted on owner meta-judgment the same day they landed
        (see _revertNote in the overlay) -- the model started building Nashor's
        Tooth as core on both, and neither builds it as a staple in the live
        meta. The floor being textually indefensible did not make the raised
        value produce better builds.
        """
        eff = _know(profiles.FORMULAS, "Nilah").get("asEfficiency")
        assert eff and eff >= 0.7, f"Nilah asEfficiency={eff}, back at the floor"

    def test_twisted_fate_and_kennen_stay_reverted(self):
        """The revert is an owner decision; a future 'cleanup' re-raising them
        should have to delete this test and argue the case, not slip through."""
        for name in ("Twisted Fate", "Kennen"):
            eff = _know(profiles.FORMULAS, name).get("asEfficiency")
            assert eff == 0.2, f"{name} asEfficiency={eff}, expected the reverted 0.2"

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


# ---------------------------------------------------------------------------
# RANK TIERS MUST NOT BE STORED AS SEPARATE RATIOS
#
# A tooltip's "110 / 130 / 150 / 170% AD" is ONE ratio that scales with ability
# rank, and 63 components store it that way. Graves' Detonation and Urgot's
# Purge bolt were extracted as four separate same-stat ratios instead, and the
# engine sums every ratio in the list, so they were charged 560% and 125% AD at
# every rank. On Graves that made End of the Line roughly three times its real
# damage and turned an engine enumeration of his best damage build into a
# zero-attack-speed ability-haste build.
# ---------------------------------------------------------------------------


def _same_stat_ratio_groups():
    import collections
    import web.fight_engine as fe
    for champion, record in fe.FORMULAS.items():
        for slot, ability in (record.get("abilities") or {}).items():
            for comp in (ability.get("damage") or []):
                ratios = comp.get("ratios") or []
                counts = collections.Counter(
                    r.get("stat") for r in ratios
                    if isinstance(r.get("pct"), (int, float)))
                for stat, n in counts.items():
                    if n > 1:
                        yield champion, slot, comp.get("name"), stat, [
                            r.get("pct") for r in ratios if r.get("stat") == stat]


def test_no_component_stores_rank_tiers_as_repeated_ratios():
    """Four strictly increasing same-stat ratios is a rank list, not a sum.

    Graves' PASSIVE is the legitimate shape and must keep passing: its
    [72, 24, 24, 24] really is four shotgun bullets that really do add up.
    """
    offenders = []
    for champion, slot, name, stat, pcts in _same_stat_ratio_groups():
        if len(pcts) == 4 and all(
                b > a for a, b in zip(pcts, pcts[1:])):
            offenders.append(f"{champion} {slot} {name} {stat}={pcts}")

    assert not offenders, (
        "rank tiers stored as separate ratios; use one entry with a rank-list "
        "pct: " + "; ".join(offenders))


def test_the_legitimately_additive_shape_is_left_alone():
    import web.fight_engine as fe
    passive = next(c for c in fe.FORMULAS["Graves"]["abilities"]["P"]["damage"]
                   if c["name"] == "Passive Auto (non-critical)")
    pcts = [r["pct"] for r in passive["ratios"]]

    assert pcts == [72, 24, 24, 24], pcts


def test_the_two_corrected_components_now_scale_by_rank():
    import web.fight_engine as fe
    for champion, slot, name in [("Graves", "1", "Detonation"),
                                 ("Urgot", "2", "Purge bolt")]:
        comp = next(c for c in fe.FORMULAS[champion]["abilities"][slot]["damage"]
                    if c["name"] == name)
        assert len(comp["ratios"]) == 1, comp["ratios"]
        assert isinstance(comp["ratios"][0]["pct"], list), comp["ratios"]


def test_graves_crit_pellets_carry_the_7_3_rate():
    """Six bullets, each at 1.5x its normal value. 288% AD, not 280%.

    The scraped tooltip said "by 30%", which is the pre-7.3 rate; the client
    says 50%, and the 7.3 note "Shotgun Critical Strike Damage rate: 1.3 -> 1.5"
    is the same number stated as a rate. Extraction had 130 + 30x5 = 280%,
    matching neither the old rate (249.6%) nor the new one.
    """
    import web.fight_engine as fe
    crit = next(c for c in fe.FORMULAS["Graves"]["abilities"]["P"]["damage"]
                if c["name"] == "Passive Auto (critical)")
    plain = next(c for c in fe.FORMULAS["Graves"]["abilities"]["P"]["damage"]
                 if c["name"] == "Passive Auto (non-critical)")
    crit_pcts = [r["pct"] for r in crit["ratios"]]
    plain_pcts = [r["pct"] for r in plain["ratios"]]

    assert plain_pcts == [72, 24, 24, 24], plain_pcts
    assert len(crit_pcts) == 6, "a critical strike fires six bullets"
    assert crit_pcts == [72 * 1.5] + [24 * 1.5] * 5, crit_pcts
    assert sum(crit_pcts) == 288


def test_the_site_tooltip_matches_the_modelled_rate():
    """The page said 30% while the engine was told 50%; both are read by users."""
    import json
    details = json.loads(
        (Path(__file__).resolve().parents[1] / "web-next" / "src" / "data"
         / "champion_details.json").read_text(encoding="utf-8"))
    passive = next(a for a in details["graves"]["abilities"] if a["slot"] == "P")

    assert "by 50%" in passive["text"]
    assert "by 30%" not in passive["text"]
