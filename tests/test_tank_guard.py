"""The tank-identity guard: prompt authority, now enforced.

gemini-3.5-flash-lite built Rod of Ages / Riftmaker / Rabadon's on Malphite
three runs out of three, straight past `approvedBuildPaths: ["tank"]` marked
AUTHORITATIVE in the prompt, and the validator shipped it -- it checks item
legality, not build-path compliance. These tests pin the enforcement that was
added in response, using the actual failing builds from that measured run.
"""
from web.advisor import profiles
from web.advisor.validate import tank_identity_violations

MALPHITE = profiles.build_identity_profile("Malphite")

# What gemini-3.6-flash actually built (run 1), and what the lite built.
TANK_BUILD = ["sunfire-aegis", "iceborn-gauntlet", "abyssal-mask",
              "amaranths-twinguard", "searing-crown"]
LITE_RUN_2 = ["rod-of-ages", "sunfire-aegis", "riftmaker",
              "abyssal-mask", "rabadons-deathcap"]
LITE_RUN_3 = ["rod-of-ages", "riftmaker", "cosmic-drive",
              "abyssal-mask", "rabadons-deathcap"]


class TestTankGuard:
    def test_malphite_derives_a_tank_identity(self):
        """The guard keys off this; if the derivation changes, so does coverage."""
        assert MALPHITE.get("primaryBuildPath") == "tank"

    def test_a_real_tank_build_passes(self):
        assert tank_identity_violations(TANK_BUILD, MALPHITE) == []

    def test_the_measured_lite_failures_are_caught(self):
        for build in (LITE_RUN_2, LITE_RUN_3):
            violations = tank_identity_violations(build, MALPHITE)
            assert violations, f"shipped-in-production failure not caught: {build}"

    def test_one_ap_item_is_tolerated(self):
        """3 Defense + 1 Magic + 1 flex is a normal tank build with a damage
        spike, not a violation."""
        build = ["sunfire-aegis", "abyssal-mask", "amaranths-twinguard",
                 "riftmaker", "thornmail"]
        assert tank_identity_violations(build, MALPHITE) == []

    def test_non_tank_identity_is_untouched(self):
        gwen = profiles.build_identity_profile("Gwen")
        ap_build = ["nashors-tooth", "riftmaker", "rabadons-deathcap",
                    "zhonyas-hourglass", "infinity-orb"]
        assert tank_identity_violations(ap_build, gwen) == []

    def test_curated_variant_rules_win(self):
        """Nunu's curated maximumAPItems is 2, so two Magic items are legal on
        him where the default cap of 1 would flag them."""
        nunu = profiles.build_identity_profile("Nunu & Willump")
        build = ["sunfire-aegis", "abyssal-mask", "amaranths-twinguard",
                 "riftmaker", "rabadons-deathcap"]
        assert tank_identity_violations(build, nunu) == []

    def test_player_locks_loosen_instead_of_deadlocking(self):
        """Two locked Magic items on a tank must not make the request
        unrepairable: the lock is the player overriding the identity."""
        build = ["rod-of-ages", "riftmaker", "sunfire-aegis",
                 "abyssal-mask", "amaranths-twinguard"]
        assert tank_identity_violations(build, MALPHITE) != []  # unlocked: flagged
        assert tank_identity_violations(
            build, MALPHITE, item_locks=["rod-of-ages", "riftmaker"]) == []
