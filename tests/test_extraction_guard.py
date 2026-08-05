"""A re-extraction must not replace a good CSV with an empty one.

The frames stay on disk, so extraction is re-runnable and the batch runner
re-does any session holding fewer than 45 win rates. That is the right policy
until the extraction API runs out of quota mid-batch: the runs after the wall
read ZERO win rates and wrote them straight over the files they were sent to
improve. lucian_20260804_1404 went from 43 win rates to 0 that way, and nothing
in the output said anything was lost.

The frames survived, so it was recoverable. It should not have needed
recovering.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract_frames import _winrate_count  # noqa: E402

FIELDS = ["rank", "player_name", "winrate", "score", "games", "champion"]


def write_csv(path: Path, filled: int, total: int = 50) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for i in range(1, total + 1):
            w.writerow({
                "rank": i,
                "player_name": f"player{i}",
                "winrate": "62.5%" if i <= filled else "",
                "score": "1234" if i <= filled else "",
                "games": "40" if i <= filled else "",
                "champion": "Lucian",
            })


class TestWinRateCount:
    def test_it_counts_win_rates_not_rows(self, tmp_path):
        """The exact distinction the guard turns on. A credit-starved run still
        writes all 50 rows; every one of them is blank."""
        p = tmp_path / "extracted.csv"
        write_csv(p, filled=0)
        assert sum(1 for _ in csv.DictReader(p.open(encoding="utf-8"))) == 50
        assert _winrate_count(p) == 0

    def test_a_partial_extraction_counts_what_it_got(self, tmp_path):
        p = tmp_path / "extracted.csv"
        write_csv(p, filled=43)
        assert _winrate_count(p) == 43

    def test_no_file_is_zero_not_an_error(self, tmp_path):
        """First extraction of a session: nothing to protect, so nothing blocks."""
        assert _winrate_count(tmp_path / "nothing.csv") == 0

    def test_an_unreadable_file_is_zero(self, tmp_path):
        """A corrupt file is not evidence of good data worth keeping, and
        raising here would break the first extraction of a session that has a
        junk CSV left over from something else."""
        p = tmp_path / "extracted.csv"
        p.write_bytes(b"\xff\xfe\x00not a csv at all\x00")
        assert _winrate_count(p) == 0


class TestThePromotionRule:
    """The comparison the writer makes, stated on its own.

    _winrate_count is what feeds it, and these pin the direction so a later
    refactor cannot quietly invert the test into "replace unless better".
    """

    def test_an_empty_run_does_not_replace_a_good_file(self, tmp_path):
        p = tmp_path / "extracted.csv"
        write_csv(p, filled=43)
        assert 0 < _winrate_count(p), "an empty run must be refused against 43"

    def test_an_improvement_replaces(self, tmp_path):
        p = tmp_path / "extracted.csv"
        write_csv(p, filled=36)
        assert not (50 < _winrate_count(p)), "a 50-rate run must be allowed over 36"

    def test_an_equal_run_replaces(self, tmp_path):
        """Re-running after a parser fix usually lands on the same count, and
        refusing that would make the guard block ordinary maintenance."""
        p = tmp_path / "extracted.csv"
        write_csv(p, filled=42)
        assert not (42 < _winrate_count(p))
