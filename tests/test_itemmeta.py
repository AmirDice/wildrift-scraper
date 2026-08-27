"""Item metadata, the mandatory audit, and the conservative pre-filter."""
from __future__ import annotations

from web.advisor import itemmeta, profiles


def _for(name: str, **kwargs):
    derived = profiles.profile(name, log=False)
    return itemmeta.filter_candidates(
        profiles.CHAMPIONS[name], derived["combatProfile"],
        derived.get("scalingProfile", {}), **kwargs)


def _audit(name: str):
    derived = profiles.profile(name, log=False)
    return itemmeta.mandatory_audit(derived["combatProfile"],
                                    derived.get("scalingProfile", {}),
                                    profiles.build_identity(name))


class TestMandatoryAudit:
    def test_hecarim_is_audited_on_spellblade_not_on_hit_stacking(self):
        audit = _audit("Hecarim")
        assert "trinity-force" in audit
        assert "guinsoos-rageblade" not in audit
        assert "runaans-hurricane" not in audit
        assert "nashors-tooth" not in audit

    def test_a_true_on_hit_carry_is_audited_on_on_hit_items(self):
        audit = _audit("Ashe")
        assert "guinsoos-rageblade" in audit
        assert "blade-of-the-ruined-king" in audit

    def test_a_pure_caster_has_no_kit_mechanic_items_to_audit(self):
        """Annie triggers no spellblade, on-hit or crit rule.

        She is still audited on ACTIVES, which every champion is: they were
        being skipped almost entirely otherwise, so they are a standing
        question rather than one a kit trigger has to unlock.
        """
        audit = _audit("Annie")
        assert not [s for s in audit
                    if "active" not in itemmeta.metadata(s)["passiveTags"]]
        assert audit, "actives should still be audited"

    def test_actives_are_audited_for_the_right_damage_type(self):
        """A physical assassin should not be asked to rule on Redemption."""
        magic, physical = _audit("Annie"), _audit("Zed")
        assert "zhonyas-hourglass" in magic and "galeforce" not in magic
        assert "galeforce" in physical and "zhonyas-hourglass" not in physical
        # Stat-neutral actives are relevant to anyone.
        assert "gargoyle-stoneplate" in magic and "gargoyle-stoneplate" in physical

    def test_the_audit_stays_small_enough_to_be_worth_answering(self):
        """Every entry costs an explicit verdict, so an unbounded list quietly
        becomes the whole response."""
        for name in profiles.CHAMPIONS:
            assert len(_audit(name)) <= itemmeta._MAX_AUDIT_ITEMS, name


class TestPreFilter:
    def test_it_removes_almost_nothing(self):
        """The filter exists to remove the impossible. If it starts trimming
        broadly it is silently narrowing every build."""
        kept, removed = _for("Hecarim", enemies_known=True)
        assert len(removed) <= 3
        assert len(kept) > 90

    def test_reactive_items_stay_in_the_pool_without_an_enemy_team(self):
        """Owner decision (2026-08-04): reactive items are standard buys, not
        counter-buys. Mortal Reminder is a 64% pick on Vayne's top 50, bought
        with no knowledge of the enemy comp either, and the unknown-enemy
        prompt now assumes a typical composition -- so there IS something to
        react to. Withholding them asked the model to out-build a ladder it
        was not allowed to imitate."""
        kept_unknown, removed_unknown = _for("Hecarim", enemies_known=False)
        for slug in ("serpents-fang", "mortal-reminder", "maw-of-malmortius"):
            assert slug in kept_unknown, f"{slug} withheld despite the policy change"
        withheld = {r["item"] for r in removed_unknown}
        assert not {"serpents-fang", "mortal-reminder",
                    "morellonomicon", "maw-of-malmortius"} & withheld

        kept_known, _ = _for("Hecarim", enemies_known=True)
        assert "serpents-fang" in kept_known

    def test_ranged_only_items_are_withheld_from_melee_champions(self):
        kept_melee, removed = _for("Hecarim", enemies_known=True)
        assert "runaans-hurricane" not in kept_melee
        assert any(r["item"] == "runaans-hurricane" for r in removed)

        kept_ranged, _ = _for("Ashe", enemies_known=True)
        assert "runaans-hurricane" in kept_ranged

    def test_a_requested_damage_path_filters_the_other_path(self):
        kept, _ = _for("Annie", damage_path="ap", enemies_known=True)
        assert "infinity-edge" not in kept

    def test_every_removal_carries_a_reason(self):
        for name in ("Hecarim", "Ashe", "Annie"):
            _, removed = _for(name, enemies_known=False)
            assert all(r.get("reason") for r in removed)


class TestMetadata:
    def test_runaans_is_ranged_only_despite_the_garbled_text(self):
        """The item text reads 'cannot only be used by melee champions'. Either
        way that sentence is untangled, melee cannot build it."""
        meta = itemmeta.metadata("runaans-hurricane")
        assert meta["meleeAllowed"] is False
        assert meta["rangedAllowed"] is True

    def test_hard_exclusive_groups_are_reflected_on_the_items(self):
        assert "spellblade" in itemmeta.metadata("trinity-force")["exclusiveGroups"]
        assert "armor-penetration" in itemmeta.metadata("black-cleaver")["exclusiveGroups"]

    def test_terminus_is_in_the_armor_penetration_group(self):
        """Verified in-game: it cannot be built with Black Cleaver."""
        assert "armor-penetration" in itemmeta.metadata("terminus")["exclusiveGroups"]

    def test_guardian_angel_is_late_strategic_not_reactive(self):
        meta = itemmeta.metadata("guardian-angel")
        assert meta["lateGameStrategic"] is True
        assert meta["situationalTags"] == []

    def test_every_pool_item_produces_metadata(self):
        for slug in itemmeta.completed_items():
            meta = itemmeta.metadata(slug)
            assert meta["slug"] == slug
            assert meta["tempoProfile"] in ("early", "early-mid", "mid-late", "late")

    def test_structured_metadata_fields_are_present(self):
        """Part 5: completionCost, activation delay, resource dependency."""
        meta = itemmeta.metadata("trinity-force")
        assert meta["completionCost"] == meta["cost"]
        assert meta["activationDelay"] in ("immediate", "delayed")
        assert meta["resourceDependency"] in ("mana", "none")
        assert meta["tempoConfidence"] == "low"  # cost is a proxy, not proof

    def test_a_stacking_item_reads_as_delayed(self):
        """Manamune stacks its tear before it transforms -- not immediate."""
        assert itemmeta.metadata("manamune")["activationDelay"] == "delayed"

    def test_a_mana_item_reports_mana_dependency(self):
        assert itemmeta.metadata("manamune")["resourceDependency"] == "mana"


def _trace(champion, slugs):
    prof = profiles.profile(champion, log=False)
    return {t["item"]: t for t in itemmeta.item_pipeline_trace(
        slugs, profiles.CHAMPIONS[champion], prof["combatProfile"],
        prof.get("scalingProfile", {}))}


class TestItemAvailability:
    """Issues 4 & 8: Eclipse, Sundered Sky and Dusk & Dawn must REACH the model
    for appropriate champions. Not asserting they are selected -- only that the
    pipeline offers and honestly evaluates them."""

    def test_eclipse_reaches_the_candidate_pool_for_an_ad_skirmisher(self):
        t = _trace("Camille", ["eclipse"])["eclipse"]
        assert t["completedNonBoots"] and t["passedPrefilter"]
        assert t["withheldReason"] is None

    def test_sundered_sky_reaches_the_pool_for_a_melee_bruiser(self):
        t = _trace("Camille", ["sundered-sky"])["sundered-sky"]
        assert t["passedPrefilter"] and t["withheldReason"] is None

    def test_dusk_and_dawn_is_audited_for_a_spellblade_weaver(self):
        for champ in ("Hecarim", "Jax"):
            t = _trace(champ, ["dusk-and-dawn"])["dusk-and-dawn"]
            assert t["inMandatoryAudit"], champ
            assert "spellblade" in t["passiveTags"]

    def test_all_three_items_are_in_the_source_pool(self):
        for slug in ("eclipse", "sundered-sky", "dusk-and-dawn"):
            assert slug in itemmeta.completed_items(), slug


class TestItemTextCorrections:
    """Corrected passive text for items the scrape mangled.

    The prompt calls the item description the FACTUAL SOURCE, so an item whose
    text stops mid-formula is the one being described worst. Sundered Sky's
    heal clause was cut off with an unbalanced bracket and appears in almost
    every bruiser build, which is what prompted the check.
    """

    def test_the_correction_reaches_the_item_pool(self):
        text = " ".join(itemmeta.ITEMS["sundered-sky"]["passives"])
        assert "restoring Health equal to 125% of base Attack Damage" in text
        assert "deals Critically Strikes" not in text, "the garbled verb is back"

    def test_no_item_text_stops_mid_bracket(self):
        """Unbalanced parentheses are the signature of a truncated scrape.

        Guinsoo's is the known remaining one and is excluded until its real
        wording is confirmed -- a plausible guess in the factual source is
        worse than obvious damage.
        """
        known = {"guinsoos-rageblade"}
        broken = {
            slug for slug, item in itemmeta.ITEMS.items()
            for passive in (item.get("passives") or [])
            if " ".join(passive.split()).count("(") != " ".join(passive.split()).count(")")
        }
        assert broken <= known, f"newly truncated item text: {sorted(broken - known)}"

    def test_corrections_never_invent_an_item(self):
        """The overlay may only correct items that exist in the scrape."""
        import json, pathlib
        raw = json.loads(
            (pathlib.Path(itemmeta.DATA) / "item_text_corrections.json").read_text(encoding="utf-8"))
        for slug in raw:
            if not slug.startswith("_"):
                assert slug in itemmeta.ITEMS, slug

    def test_every_correction_records_where_it_came_from(self):
        """Provenance is the point: this file overrides the scraped truth."""
        import json, pathlib
        raw = json.loads(
            (pathlib.Path(itemmeta.DATA) / "item_text_corrections.json").read_text(encoding="utf-8"))
        for slug, entry in raw.items():
            if slug.startswith("_"):
                continue
            assert entry.get("_source"), f"{slug} has no _source"
            assert entry.get("_was"), f"{slug} does not record what it replaced"


class TestThreatResponseItems:
    """threats.py names WHAT answers a comp; this turns that into items.

    Before this bridge existed the enemy composition reached the item choice
    as prose alone, and the model had to recall unprompted which item applies
    anti-heal.
    """

    def test_every_category_the_threat_model_can_raise_resolves_to_items(self):
        # The categories threats.py appends to itemizableResponses.
        for category in ("armor", "magic_resist", "anti_basic_attack",
                         "burst_survival", "grievous_wounds", "shield_reduction",
                         "tenacity"):
            got = itemmeta.items_answering(category)
            assert got, f"{category} resolves to no items, so naming it says nothing"

    def test_anti_heal_names_the_items_that_actually_apply_it(self):
        got = itemmeta.items_answering("grievous_wounds")
        assert "morellonomicon" in got
        assert "chempunk-chainsword" in got

    def test_shield_reduction_is_the_two_items_that_do_it(self):
        assert set(itemmeta.items_answering("shield_reduction")) == {
            "serpents-fang", "oceanids-trident"}

    def test_boots_answer_categories_even_though_they_are_not_in_the_pool(self):
        """Mercury's Treads IS the tenacity answer, and Plated Steelcaps IS the
        answer to a lane of basic attacks. Boots occupy their own slot, so the
        five-slot candidate pool must not hide them."""
        assert "mercurys-treads" in itemmeta.items_answering("tenacity", pool=[])
        assert "plated-steelcaps" in itemmeta.items_answering("anti_basic_attack", pool=[])

    def test_a_pool_restricts_the_non_boot_answers(self):
        """A marksman must never be told Thornmail answers the enemy sustain."""
        got = itemmeta.items_answering("grievous_wounds", pool=["morellonomicon"])
        assert got == ["morellonomicon"]

    def test_stat_categories_lead_with_the_most_of_the_stat(self):
        """Cheapest-first put Knight's Vow above Randuin's Omen, which is not
        an armor answer anyone wants."""
        armor = itemmeta.items_answering("armor")
        assert armor[0] in ("frozen-heart", "thornmail", "randuins-omen")
        assert armor.index("randuins-omen") < armor.index("knights-vow")
