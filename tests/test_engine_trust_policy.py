"""Contracts for deterministic engine authority and coverage disclosure."""

from web import build_advisor as adv


def _measurement(candidate_id: str, *, champion_gap: str = "",
                 item_gap: str = "") -> dict:
    champion_gaps = ([{"limitation": champion_gap}] if champion_gap else [])
    item_gaps = ([{
        "item": "test-item",
        "status": "partial",
        "limitation": item_gap,
    }] if item_gap else [])
    return {
        "id": candidate_id,
        "engine": {
            "championMechanicsCoverage": {
                "buildRelevantGaps": champion_gaps,
            },
            "coverageGaps": item_gaps,
        },
    }


def test_gate_audits_engine_and_best_authored_candidate():
    meta = {
        "challengerScore": 110,
        "authoredBestScore": 100,
        "authoredScores": {"A": 100, "B": 92},
    }
    measured = [
        _measurement("ENGINE-D"),
        _measurement("A", champion_gap="missing-health execute is not modeled"),
        _measurement("B"),
    ]

    gate = adv._engine_win_gate(meta, measured)

    assert gate["eligible"] is False
    assert gate["marginSatisfied"] is True
    assert gate["coverageSafe"] is False
    assert gate["trustLevel"] == "advisory"
    assert gate["comparisonCandidates"] == ["ENGINE-D", "A"]
    assert any("A:" in gap and "execute" in gap
               for gap in gate["majorCoverageGaps"])


def test_gap_on_losing_authored_candidate_does_not_block_gate():
    meta = {
        "challengerScore": 110,
        "authoredBestScore": 100,
        "authoredScores": {"A": 100, "B": 92},
    }
    measured = [
        _measurement("ENGINE-D"),
        _measurement("A"),
        _measurement("B", champion_gap="recast damage is not modeled"),
    ]

    gate = adv._engine_win_gate(meta, measured)

    assert gate["eligible"] is True
    assert gate["decision"] == "auto-select-engine"
    assert gate["trustLevel"] == "authoritative-for-scenario"


def test_missing_comparison_measurement_is_never_coverage_safe():
    gate = adv._engine_win_gate({
        "challengerScore": 110,
        "authoredBestScore": 100,
        "authoredScores": {"A": 100},
    }, [_measurement("ENGINE-D")])

    assert gate["eligible"] is False
    assert gate["coverageSafe"] is False
    assert "A: measurement missing" in gate["majorCoverageGaps"]


def test_stats_only_item_with_missing_combat_effect_is_major():
    assert adv._coverage_gap_is_major({
        "item": "example",
        "status": "stats_only",
        "limitation": "The combat passive is not modeled.",
    }) is True
    assert adv._coverage_gap_is_major({
        "item": "example",
        "status": "stats_only",
        "limitation": "The passive is already represented by printed stats.",
    }) is False


def test_missing_scores_return_explicit_insufficient_data_contract():
    gate = adv._engine_win_gate({}, [])

    assert gate["eligible"] is False
    assert gate["decision"] == "defer"
    assert gate["trustLevel"] == "insufficient-data"
    assert gate["marginSatisfied"] is False
    assert gate["coverageSafe"] is False


def test_tournament_discloses_declared_partial_item_coverage():
    candidate = {
        "id": "ENGINE-D",
        "archetype": "ad-crit",
        "hypothesis": "coverage contract",
        "items": ["hexoptics-c44", "infinity-edge", "rapid-firecannon",
                  "lord-dominiks-regard", "bloodthirster"],
        "boots": "berserkers-greaves",
        "runes": {
            "keystone": "Lethal Tempo",
            "primaryTree": "Precision",
            "minors": ["Brutal", "Cut Down", "Legend: Alacrity"],
            "flex": "Bone Plating",
        },
        "summoners": ["Flash", "Barrier"],
    }

    measured = adv._simulate_tournament("Jinx", [candidate])
    engine = measured[0]["engine"]
    hexoptics = next(row for row in engine["coverageGaps"]
                     if row["item"] == "hexoptics-c44")

    assert hexoptics["status"] == "partial"
    assert hexoptics["severity"] == "major"
    assert engine["coverageSummary"]["engineAuthoritative"] is False
    assert engine["coverageSummary"]["itemMajorGapCount"] == 1

