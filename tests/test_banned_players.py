"""Permabanned accounts: shown on the board, excluded from every aggregate.

Distinct from boosting adverts, and deliberately handled the opposite way
round. An advert loses its NAME because the name is the advertisement. A ban
keeps its name and gains a tag, because there the identity is the useful part.
Only the ban costs the account its numbers. An advertising name says how an
account is MARKETED, not how it is played.

Detection is a curated list, never a heuristic. Nothing in a win rate proves a
ban, and inferring one would accuse real players of cheating for being good --
the same mistake the narrow advertising regex exists to avoid.
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from web.integrity import (  # noqa: E402
    BANNED_LABEL, HIDDEN_LABEL, ban_reason, counts_toward_aggregates,
    display_name, is_advertising_account, is_banned_account)

ROOT = pathlib.Path(__file__).resolve().parent.parent
BANNED_FILE = ROOT / "data" / "banned_players.json"


class TestTheList:
    def test_the_recorded_accounts_are_recognised(self):
        entries = json.loads(BANNED_FILE.read_text(encoding="utf-8"))["players"]
        assert entries, "expected at least one recorded ban to guard"
        for entry in entries:
            assert is_banned_account(entry["name"]), entry["name"]
            assert ban_reason(entry["name"]) == entry["reason"]

    def test_matching_ignores_case_and_punctuation(self):
        """The same fold the player index uses, so a name that matches there
        matches here."""
        for variant in ("will will well", "WILL WILL WELL", "WillWillWell",
                        "Will-Will-Well"):
            assert is_banned_account(variant), variant

    def test_an_ordinary_player_is_untouched(self):
        """Kasper and Tớ Là Lùm sat next to a banned account on one board and
        must not be caught by proximity, spelling, or anything else."""
        for name in ("Kasper", "Tớ Là Lùm", "Yıldız", "Mihailo", "Kaynculata"):
            assert not is_banned_account(name), name
            assert counts_toward_aggregates(name), name

    def test_nothing_and_empty_are_not_bans(self):
        for value in (None, "", "   "):
            assert not is_banned_account(value)


class TestHowItDiffersFromABoostingAdvert:
    def test_a_banned_account_keeps_its_name(self):
        """The whole point of the difference. Hiding it would rewrite the board
        without saying so."""
        assert display_name("Will Will Well") == "Will Will Well"
        assert display_name("Insta wrboost25") == HIDDEN_LABEL

    def test_a_ban_is_not_detected_as_an_advert(self):
        for name in ("Will Will Well", "Mollo", "SKT T1 Mika", "beginner player"):
            assert not is_advertising_account(name), name

    def test_only_a_ban_costs_the_account_its_statistics(self):
        """An advert loses its name; a ban loses its number. Not both, and not
        the other way round."""
        assert not counts_toward_aggregates("Will Will Well")
        assert counts_toward_aggregates("Insta wrboost25")
        assert counts_toward_aggregates("Kasper")

    def test_the_label_is_not_the_hidden_label(self):
        assert BANNED_LABEL != HIDDEN_LABEL


class TestAggregatesActuallyExcludeThem:
    def test_the_loader_drops_banned_rows(self):
        """The two entries that were being counted before this existed: Will
        Will Well on Karma at 72.7% over 33 games, and SKT T1 Mika on
        Tryndamere at 74.6% over 63. Both fed champion averages."""
        import pandas as pd
        from web.integrity import counts_toward_aggregates as keep
        df = pd.DataFrame([
            {"player_name": "Kasper", "winrate": 55.0},
            {"player_name": "Will Will Well", "winrate": 72.7},
            {"player_name": "SKT T1 Mika", "winrate": 74.6},
            {"player_name": "Insta wrboost25", "winrate": 93.8},
        ])
        kept = df[df["player_name"].apply(keep)]
        assert list(kept["player_name"]) == ["Kasper", "Insta wrboost25"]


class TestTitlesAreNotForAdverts:
    """Aggregates and titles answer different questions.

    An advert's games count toward champion averages -- an average carries no
    name. A title IS a name, and the day the two questions were collapsed into
    one predicate, "Insta YushinWR" led Morgana's champion page, "Insta
    wrboost25" led Orianna's, and the Hall of Fame mastery record went to
    "Insta wrsamboost". These tests keep the questions apart.
    """

    def test_an_advert_counts_but_cannot_be_crowned(self):
        from web.integrity import counts_toward_aggregates, eligible_for_title
        assert counts_toward_aggregates("Insta wrboost25")
        assert not eligible_for_title("Insta wrboost25")

    def test_a_ban_fails_both(self):
        from web.integrity import counts_toward_aggregates, eligible_for_title
        assert not counts_toward_aggregates("Will Will Well")
        assert not eligible_for_title("Will Will Well")

    def test_a_shown_anyway_exception_is_title_eligible(self):
        """The owner chose to display this name; a name fit for the board is
        fit for a title."""
        from web.integrity import eligible_for_title
        assert eligible_for_title("DM For Boost")

    def test_an_ordinary_player_passes_both(self):
        from web.integrity import counts_toward_aggregates, eligible_for_title
        assert counts_toward_aggregates("Kasper")
        assert eligible_for_title("Kasper")

    def test_best_player_never_crowns_an_advert(self):
        """The full pipeline check: the advert holds the top Wilson score and
        still does not get the flag; the best ELIGIBLE player does."""
        import pandas as pd
        from web.data_loader import best_player_per_champion
        df = pd.DataFrame([
            {"champion": "Morgana", "rank": 3, "player_name": "Insta YushinWR",
             "winrate": 94.6, "games": 37},
            {"champion": "Morgana", "rank": 1, "player_name": "Kasper",
             "winrate": 70.0, "games": 60},
        ])
        out = best_player_per_champion(df)
        crowned = out[out["is_best_for_champ"]]
        assert list(crowned["player_name"]) == ["Kasper"]
        # the advert's score is still computed -- its number is not erased
        advert = out[out["player_name"] == "Insta YushinWR"].iloc[0]
        assert advert["confidence_wr"] > 0


class TestMixedTimestampFormats:
    """The CSV carries two timestamp shapes and both must parse.

    Carried June rows say "2026-06-13 21:48:08+00:00"; fresh extraction rows
    say "2026-08-03T13:50:57". pandas locked onto one format and coerced the
    other 6,113 rows to NaT, so the newest surviving timestamp was June: the
    site told visitors "Data collected June 13, 2026" in August, and the
    export OVERWROTE the June history snapshot -- the movers baseline -- with
    mixed data filed under June's name.
    """

    def test_both_formats_parse_and_the_max_is_the_fresh_one(self):
        import pandas as pd
        from web.data_loader import data_collected_on
        df = pd.DataFrame({"captured_at": [
            "2026-06-13 21:48:08+00:00",   # carried, timezone-aware
            "2026-08-03T13:50:57",         # fresh, ISO-T naive
        ], "winrate": [50.0, 50.0]})
        assert data_collected_on(df) == "August 3, 2026"

    def test_garbage_timestamps_do_not_crash_or_win(self):
        import pandas as pd
        from web.data_loader import data_collected_on
        df = pd.DataFrame({"captured_at": ["not a date", None, "2026-08-05T09:00:00"]})
        assert data_collected_on(df) == "August 5, 2026"


class TestConsistencyIsExcessSpread:
    """winrate_std measures the spread SAMPLING CANNOT EXPLAIN, not raw std.

    Raw std was mostly a games counter: a 20-game win rate carries ~11 points
    of binomial noise on its own, so the "least consistent" list was the
    least-played list with the three strongest boards on it, and noise
    explained >70% of the number for 120 of 140 champions.
    """

    @staticmethod
    def _summary(rows):
        import pandas as pd
        from web.data_loader import champion_summary
        return champion_summary(pd.DataFrame(rows))

    def test_uniform_players_with_noisy_samples_read_near_zero(self):
        # 50 players, all truly ~55%, few games each: raw std would be large,
        # excess must be small.
        import random
        rng = random.Random(7)
        rows = [{"champion": "A", "rank": i + 1, "player_name": f"p{i}", "score": 8000,
                 "games": 25, "winrate": 100 * min(1, max(0, rng.gauss(0.55, (0.55 * 0.45 / 25) ** 0.5)))}
                for i in range(50)]
        out = self._summary(rows)
        assert float(out["winrate_std"].iloc[0]) < 3.0

    def test_genuine_player_spread_survives(self):
        # Two real populations, 200 games each: measurement noise is tiny, the
        # 10-point split between them is real and must remain visible.
        rows = ([{"champion": "B", "rank": i + 1, "player_name": f"lo{i}", "score": 8000,
                  "games": 200, "winrate": 50.0} for i in range(25)]
                + [{"champion": "B", "rank": 26 + i, "player_name": f"hi{i}", "score": 8000,
                    "games": 200, "winrate": 60.0} for i in range(25)])
        out = self._summary(rows)
        # 25 players at 50% + 25 at 60% is sd ~5.05; subtracting the ~12.3
        # pct^2 of expected sampling variance leaves ~3.6. The point is that
        # it stays clearly ABOVE zero while the uniform board reads near it.
        assert float(out["winrate_std"].iloc[0]) > 3.0
