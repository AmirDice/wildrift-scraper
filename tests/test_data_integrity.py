"""Guards for the data the LLM and the engine actually read.

Every failure encoded here was a real bug that shipped silently and was found
by hand weeks or months later: an ability extracted as dealing nothing, prose
written into a numeric field, a derived file left stale after its source
changed. None of it broke a page or raised an exception -- the site rendered,
the engine scored, the build generated, and the number was simply wrong.

So these are not unit tests of functions. They assert properties of the data
files, which is where this project's defects actually live.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.audit_formulas as audit

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
WEB = ROOT / "web-next" / "src" / "data"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def formulas() -> dict:
    return load(DATA / "ability_formulas.json")


@pytest.fixture(scope="module")
def champions() -> list[dict]:
    return load(DATA / "champions_wr.json")


def records(formulas: dict) -> dict:
    return {k: v for k, v in formulas.items() if not k.startswith("_")}


def numbers_in(value) -> list[float]:
    """Every number a formula field asserts, whatever shape it is stored in."""
    if isinstance(value, dict):
        value = value.get("lvlRange") or []
    if not isinstance(value, list):
        value = [value]
    return [v for v in value if isinstance(v, (int, float))]


# --------------------------------------------------------------------------
# the audit, as a test
# --------------------------------------------------------------------------

class TestAbilityExtraction:
    def test_no_ability_that_states_damage_is_extracted_as_empty(self):
        """The failure that hid Heimerdinger's W dealing zero for months."""
        hard = audit.collect()["hard"]
        assert hard == [], (
            "abilities whose tooltip states damage they deal, extracted with no damage "
            f"component: {[(c, s, n) for c, s, n, _ in hard]}"
        )

    def test_known_gaps_are_all_still_genuinely_empty(self):
        """A gap that got fixed must leave the list, or it hides a regression."""
        stale = audit.collect()["staleKnownGaps"]
        assert stale == [], f"no longer empty, drop from KNOWN_GAPS: {stale}"

    def test_grounding_rejects_nothing_new(self):
        """Rejections are listed rather than counted so a NEW one fails here.

        Fix the entry or add it deliberately; do not raise a threshold.
        """
        known = {("Pyke", "4")}
        found = {(c, s) for c, s, _, _ in audit.collect()["ungrounded"]}
        assert found <= known, f"new grounding rejections: {sorted(found - known)}"


class TestFormulaShape:
    def test_every_champion_and_form_has_formulas(self, formulas, champions):
        expected = {c["name"] for c in champions}
        expected |= {f["name"] for c in champions for f in (c.get("forms") or [])}
        assert expected <= set(records(formulas)), (
            f"missing formulas: {sorted(expected - set(records(formulas)))}")

    def test_numeric_fields_hold_numbers(self, formulas):
        """Sett's shield once had base "grit consumed", which reached the
        exported JSON and broke the typed frontend."""
        bad = []
        for name, rec in records(formulas).items():
            for slot, ability in (rec.get("abilities") or {}).items():
                for key in ("damage", "defensive", "steroids"):
                    for part in ability.get(key) or []:
                        if not isinstance(part, dict):
                            bad.append(f"{name}[{slot}] {key}: {part!r:.40}")
                            continue
                        for field in ("base", "flat", "pct", "hits"):
                            raw = part.get(field)
                            if raw is None:
                                continue
                            flat = raw.get("lvlRange") if isinstance(raw, dict) else raw
                            values = flat if isinstance(flat, list) else [flat]
                            if any(not isinstance(v, (int, float)) for v in values):
                                bad.append(f"{name}[{slot}] {key}.{field}={raw!r:.40}")
        assert bad == [], f"non-numeric values in numeric fields: {bad}"

    def test_no_released_champion_simulates_to_zero_damage(self, formulas):
        """Components can exist and still compute to nothing, which no other
        check sees. Cho'Gath is exempt: he is unreleased and his tooltips are
        placeholders with no numbers at all."""
        unreleased = {"Cho'Gath"}
        dead = []
        for name, rec in records(formulas).items():
            if name in unreleased:
                continue
            live = False
            for ability in (rec.get("abilities") or {}).values():
                for part in ability.get("damage") or []:
                    if not isinstance(part, dict):
                        continue
                    if any(v for v in numbers_in(part.get("base"))):
                        live = True
                    if any(any(v for v in numbers_in(r.get("pct")))
                           for r in part.get("ratios") or []):
                        live = True
            if not live:
                dead.append(name)
        assert dead == [], f"champions whose whole kit computes to zero damage: {dead}"


class TestCuratedFilesMatchTheRoster:
    def test_heal_targets_point_at_real_abilities(self, formulas):
        targets = load(DATA / "heal_targets.json")["champions"]
        recs = records(formulas)
        missing = [f"{champ}[{slot}]"
                   for champ, slots in targets.items()
                   for slot in slots
                   if champ not in recs or slot not in (recs[champ].get("abilities") or {})]
        assert missing == [], f"heal_targets references abilities that do not exist: {missing}"

    def test_aoe_ult_list_names_real_champions(self, champions):
        names = {c["name"] for c in champions}
        listed = set(load(DATA / "ult_shape.json")["aoeUlts"])
        assert listed <= names, f"ult_shape names unknown champions: {sorted(listed - names)}"

    def test_kit_amps_point_at_real_champions(self, formulas):
        amps = load(DATA / "kit_amps.json")["champions"]
        assert set(amps) <= set(records(formulas)), (
            f"kit_amps names unknown champions: {sorted(set(amps) - set(records(formulas)))}")


# --------------------------------------------------------------------------
# derived files: stale data renders fine and is simply wrong
# --------------------------------------------------------------------------

class TestDerivedDataIsFresh:
    def test_frontend_builds_match_the_source(self):
        """builds.json is a copy of champion_builds.json. It has drifted before,
        leaving the site serving builds the source no longer had."""
        assert load(WEB / "builds.json") == load(DATA / "champion_builds.json"), (
            "web-next/src/data/builds.json is stale; it is written from "
            "data/champion_builds.json by scripts/build_champions_llm.py")

    def test_engine_formulas_match_the_source(self):
        """engine.json must equal what the exporter builds from the sources.

        It is no longer a verbatim copy of ability_formulas.json: combos come
        from champion_combos.json and recovered durations and every-N counts
        from ability_conditions.json, both applied at export. Rather than
        listing the fields that may differ -- which needs editing every time an
        overlay is added, and silently stops checking whatever is forgotten --
        this applies the SAME overlays the exporter does and compares the whole
        thing.
        """
        from scripts.export_engine_data import (
            _apply_recovered_conditions, apply_cooldown_corrections,
        )

        expected = load(DATA / "ability_formulas.json")
        _apply_recovered_conditions(expected)
        apply_cooldown_corrections(expected)
        for name, entry in (load(DATA / "champion_combos.json")["champions"]).items():
            if name in expected and entry.get("combo"):
                expected[name]["combo"] = entry["combo"]

        assert load(WEB / "engine.json")["formulas"] == expected, (
            "engine.json is stale; re-run python -m scripts.export_engine_data")

    def test_owner_verified_cooldowns_reach_the_engine(self):
        """A cooldown read off the game must be what the engine ships.

        The scrape gave Kayn's two forms DIFFERENT cooldowns and both sets were
        wrong; the game gives base, Shadow Assassin and Rhaast the same ones.
        This checks the overlay is applied rather than merely present.
        """
        overlay = load(DATA / "ability_cooldown_corrections.json")["champions"]
        shipped = load(WEB / "engine.json")["formulas"]
        for name, entry in overlay.items():
            for slot, fix in (entry.get("abilities") or {}).items():
                got = shipped[name]["abilities"][slot]["cooldowns"]
                assert got == [float(v) for v in fix["cooldowns"]], f"{name} slot {slot}"

    def test_both_kayn_forms_share_their_cooldowns(self):
        """The specific error: forms change what an ability DOES, not how often
        it can be cast. Two different cooldown sets is the bug's signature."""
        shipped = load(WEB / "engine.json")["formulas"]
        for slot in ("1", "2", "3", "4"):
            assert (shipped["Kayn"]["abilities"][slot]["cooldowns"]
                    == shipped["Kayn (Rhaast)"]["abilities"][slot]["cooldowns"]), slot

    def test_recovered_conditions_reach_the_engine(self):
        """A duration recovered into the overlay must be in the exported data.

        Without this the recovery silently does nothing: the engines read
        durationS, and an overlay that never lands leaves every buff permanent
        again -- the exact bug it was written to fix.
        """
        overlay = load(DATA / "ability_conditions.json")
        engine = load(WEB / "engine.json")["formulas"]
        missing = []
        for name, entries in (overlay.get("durations") or {}).items():
            for key, value in entries.items():
                slot, _, idx = key.partition(":")
                steroids = ((engine.get(name, {}).get("abilities") or {})
                            .get(slot, {}).get("steroids") or [])
                if not idx.isdigit() or int(idx) >= len(steroids):
                    continue
                if steroids[int(idx)].get("durationS") != value["seconds"]:
                    missing.append(f"{name}[{key}]")
        assert missing == [], (
            f"recovered durations did not reach engine.json: {missing[:5]}; "
            "re-run python -m scripts.export_engine_data")

    def test_roster_holds_champions_and_engine_holds_forms(self, champions):
        """A transform form is a kit, not a champion: the engine needs it so it
        can simulate the transformed state, the roster must not have it or the
        form appears in every champion list and enemy picker."""
        roster = load(WEB / "roster.json")
        engine = load(WEB / "engine.json")["champions"]
        forms = {f["name"] for c in champions for f in (c.get("forms") or [])}
        assert forms, "expected at least one transform form in the scrape"
        assert not (forms & set(roster)), f"forms leaked into the roster: {sorted(forms & set(roster))}"
        assert forms <= set(engine), f"forms missing from the engine: {sorted(forms - set(engine))}"

    def test_champion_details_covers_every_champion_and_form(self, champions):
        details = load(WEB / "champion_details.json")
        expected = {c["slug"] for c in champions}
        expected |= {f["slug"] for c in champions for f in (c.get("forms") or [])}
        assert expected <= set(details), (
            "champion_details.json is stale; re-run python -m scripts.export_champion_details. "
            f"missing: {sorted(expected - set(details))}")
