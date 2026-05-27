"""Append-row CSV writer for scraped leaderboard rows.

The CSV is created with a header on first write; subsequent writes append.
Designed to survive crashes/restarts so the scraper can checkpoint as it goes.

Schema (one row per leaderboard entry):

    champion, rank, player_name, winrate, captured_at

`captured_at` is an ISO-8601 UTC timestamp.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


FIELDNAMES = ["champion", "rank", "player_name", "winrate", "captured_at"]


@dataclass
class LeaderboardRow:
    champion: str
    rank: int
    player_name: str
    winrate: float | None
    captured_at: str = ""

    def __post_init__(self) -> None:
        if not self.captured_at:
            self.captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")


class CSVWriter:
    """Thin append-only CSV writer with header bootstrapping."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._needs_header = not self.path.exists() or self.path.stat().st_size == 0

    def write(self, row: LeaderboardRow) -> None:
        self.write_many([row])

    def write_many(self, rows: Iterable[LeaderboardRow]) -> None:
        rows = list(rows)
        if not rows:
            return
        with self.path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            if self._needs_header:
                writer.writeheader()
                self._needs_header = False
            for row in rows:
                writer.writerow(asdict(row))
