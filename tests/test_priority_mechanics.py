"""Focused contracts for the first champion-mechanics coverage pass."""

from web import fight_engine as fe


def _component(name: str, slot: str, component: str):
    return next(
        c for c in fe.FORMULAS[name]["abilities"][slot]["damage"]
        if c.get("name") == component
    )


def test_priority_numeric_terms_are_structured():
    assert _component("Sett", "1", "Knuckle Down")["crossRatios"][0]["pctPerStat"] == [
        0.01, 0.015, 0.02, 0.025
    ]
    assert _component("Sett", "2", "Haymaker Center")["gritScale"]["perAd"] == 0.00275
    assert _component("Gwen", "P", "Thousand Cuts on-hit")["crossRatios"]
    assert _component("Ambessa", "P", "Drakehound's Step Empowered Attack")["baseAdd"] == 2.5
    assert _component("Lucian", "1", "Piercing Light")["ratios"][0]["pct"] == [
        65, 85, 105, 125
    ]


def test_priority_stateful_mechanics_are_present():
    pantheon_w = _component("Pantheon", "2", "Shield Vault (Mortal Will empowered attack)")
    assert pantheon_w["hits"] == 3
    assert pantheon_w["mortalWill"] is True
    assert fe.FORMULAS["Gwen"]["abilities"]["4"]["recastChain"] is True
    assert fe.FORMULAS["Aatrox"]["abilities"]["1"]["recastMultiplier"] == [1, 1.25, 1.5625]
    assert fe.FORMULAS["Hecarim"]["abilities"]["1"]["nextCastMultiplier"] == 1.2


def test_malphite_armor_and_lucian_level_scaling_reach_stats():
    armor_steroid = fe.FORMULAS["Malphite"]["abilities"]["2"]["steroids"][0]
    assert armor_steroid["pct"] == [25, 30, 35, 40]
    assert _component("Malphite", "2", "Thunderclap empowered first attack")["empowerLimit"] == 1
    assert fe.FORMULAS["Pantheon"]["abilities"]["1"]["tapCooldownRefundPct"] == 0.6

    lucian_mech = next(m for m in fe.FORMULAS["Lucian"]["mechanics"]
                       if m.get("kind") == "doubleShot")
    assert lucian_mech["secondShotPctByLevel"][-1] == [11, 65]


def test_priority_champions_still_disclose_unfinished_mechanics():
    # This pass intentionally models the high-value numeric terms without
    # claiming that spatial, defensive, or exact cooldown interactions are done.
    for name in ("Sett", "Pantheon", "Malphite", "Gwen", "Graves",
                 "Ambessa", "Aatrox", "Hecarim", "Lucian"):
        report = fe.champion_mechanics_coverage(name)
        assert report["status"] == "partial", name
        assert report["buildRelevantGapCount"] > 0, name
