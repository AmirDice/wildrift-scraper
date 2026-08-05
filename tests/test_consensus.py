"""Best-of-N generation: sample the model several times, keep what agrees.

The problem this solves was measured, not theorised. Vayne, asked three times
on an IDENTICAL prompt, returned three different builds. Whichever one a player
happened to get was then cached and became that champion's answer for everyone
until the patch rolled.

The rule these tests protect is that the winner is always a build the model
actually authored. A per-slot majority spliced across runs would be a build no
run proposed, carrying item reasons for items it no longer contains and a
validation pass that was run against something else.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web import build_advisor as adv  # noqa: E402


def build(items, boots="berserkers-greaves", keystone="Lethal Tempo",
          minors=("Brutal", "Cut Down", "Legend: Alacrity"), **extra):
    out = {
        "items": list(items),
        "boots": boots,
        "runes": {"keystone": keystone, "minors": list(minors), "flex": "Flex"},
    }
    out.update(extra)
    return out


def samples(monkeypatch, *results):
    """Make `advise` return these builds, one per call, in order."""
    calls = iter(results)

    def fake(_champion, _role, _enemies, **_kwargs):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(adv, "advise", fake)


A = ["blade-of-the-ruined-king", "guinsoos-rageblade", "kraken-slayer",
     "terminus", "amaranths-twinguard"]
B = ["blade-of-the-ruined-king", "guinsoos-rageblade", "kraken-slayer",
     "terminus", "wits-end"]
C = ["blade-of-the-ruined-king", "guinsoos-rageblade", "runaans-hurricane",
     "infinity-edge", "bloodthirster"]


class TestTheVote:
    def test_two_matching_samples_beat_one_outlier(self, monkeypatch):
        samples(monkeypatch, build(C), build(A), build(A))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        assert res["items"] == A

    def test_the_winner_is_always_a_build_some_run_returned(self, monkeypatch):
        """Never a splice. Three-way disagreement still returns one whole run.

        A per-slot majority here would invent a build from the items that
        happen to appear twice, and nothing else in it -- the reasons, the
        purchase order, the situational swaps -- would describe that build.
        """
        samples(monkeypatch, build(A), build(B), build(C))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        assert res["items"] in (A, B, C)

    def test_an_element_every_sample_chose_survives(self, monkeypatch):
        samples(monkeypatch, build(A), build(B), build(C))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        for unanimous in ("blade-of-the-ruined-king", "guinsoos-rageblade"):
            assert unanimous in res["items"]

    def test_runes_are_voted_on_too_not_just_items(self, monkeypatch):
        """Same five items in every sample, so only the rune page can decide."""
        samples(monkeypatch,
                build(A, keystone="Conqueror"),
                build(A, keystone="Lethal Tempo"),
                build(A, keystone="Lethal Tempo"))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        assert res["runes"]["keystone"] == "Lethal Tempo"

    def test_purchase_order_is_not_part_of_the_vote(self, monkeypatch):
        """Two runs buying the same five items in a different order AGREE.

        Counting order as a disagreement would let a shuffled duplicate of the
        winning build vote against it.
        """
        shuffled = list(reversed(A))
        samples(monkeypatch, build(C), build(A), build(shuffled))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        assert sorted(res["items"]) == sorted(A)


class TestWhatItReports:
    def test_it_records_how_much_the_samples_agreed(self, monkeypatch):
        samples(monkeypatch, build(A), build(A), build(A))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        con = res["consensus"]
        assert con["runs"] == 3
        # five items + boots + keystone + three minors
        assert con["unanimous"] == con["of"] == 10

    def test_disagreement_shows_up_as_a_lower_unanimous_count(self, monkeypatch):
        samples(monkeypatch, build(A), build(A), build(B))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        con = res["consensus"]
        assert con["unanimous"] == con["of"] - 1      # amaranth's is 2/3
        assert con["votes"]["items"]["amaranths-twinguard"] == 2


class TestDegrading:
    def test_runs_of_one_never_touches_the_vote(self, monkeypatch):
        samples(monkeypatch, build(A))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=1)
        assert "consensus" not in res

    def test_a_failed_sample_does_not_fail_the_generation(self, monkeypatch):
        samples(monkeypatch, RuntimeError("upstream on fire"), build(A), build(A))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        assert res["items"] == A
        assert res["consensus"]["runs"] == 2
        assert res["consensus"]["requested"] == 3

    def test_one_surviving_sample_is_returned_unvoted(self, monkeypatch):
        """Which is exactly what a single-run generation would have produced."""
        samples(monkeypatch,
                RuntimeError("boom"), RuntimeError("boom"), build(A))
        res = adv.advise_best_of("Vayne", "dragon", [], runs=3)
        assert res["items"] == A
        assert "consensus" not in res

    def test_every_sample_failing_still_raises(self, monkeypatch):
        samples(monkeypatch, *[RuntimeError("boom")] * 3)
        with pytest.raises(RuntimeError):
            adv.advise_best_of("Vayne", "dragon", [], runs=3)

    def test_a_rejected_request_returns_immediately_without_voting(self, monkeypatch):
        """An unsupported playstyle is a bad REQUEST, not a bad sample.

        Every run would report the same thing, so voting on it would spend
        three model calls to rediscover an answer the first one already gave.
        """
        samples(monkeypatch, {"error": "'crit' is not a supported preset for Sona"},
                build(A), build(A))
        res = adv.advise_best_of("Sona", "support", [], runs=3)
        assert res["error"].startswith("'crit' is not a supported preset")
