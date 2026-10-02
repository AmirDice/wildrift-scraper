import pandas as pd

from web.data_loader import BEST_PLAYER_SCORING_VERSION, best_player_podium_per_champion


def test_podium_uses_composite_fields_and_keeps_three_rows():
    frame = pd.DataFrame(
        [
            {"champion": "Test", "rank": 1, "player_name": "A", "score": 100, "games": 100, "winrate": 60.0},
            {"champion": "Test", "rank": 2, "player_name": "B", "score": 200, "games": 80, "winrate": 65.0},
            {"champion": "Test", "rank": 3, "player_name": "C", "score": 50, "games": 30, "winrate": 90.0},
            {"champion": "Test", "rank": 4, "player_name": "D", "score": 40, "games": 2, "winrate": 100.0},
        ]
    )

    result = best_player_podium_per_champion(frame)
    podium = result[result["podium_rank"].notna()].sort_values("podium_rank")

    assert len(podium) == 3
    assert podium["podium_rank"].tolist() == [1, 2, 3]
    assert podium.iloc[0]["is_best_for_champ"]
    assert set(podium["scoring_version"]) == {BEST_PLAYER_SCORING_VERSION}
    assert podium["score_coverage"].notna().all()
    assert "D" not in podium["player_name"].tolist()


def test_combined_servers_normalize_board_position_per_server():
    frame = pd.DataFrame(
        [
            {"champion": "Test", "server": "EU", "rank": 1, "player_name": "EU1", "score": 100, "games": 80, "winrate": 60.0},
            {"champion": "Test", "server": "EU", "rank": 2, "player_name": "EU2", "score": 90, "games": 80, "winrate": 60.0},
            {"champion": "Test", "server": "CN", "rank": 1, "player_name": "CN1", "score": 100, "games": 80, "winrate": 60.0},
            {"champion": "Test", "server": "CN", "rank": 2, "player_name": "CN2", "score": 90, "games": 80, "winrate": 60.0},
        ]
    )

    result = best_player_podium_per_champion(frame)
    rows = result.set_index("player_name")

    assert rows.loc["EU1", "best_score_board"] == rows.loc["CN1", "best_score_board"]
    assert rows.loc["EU2", "best_score_board"] == rows.loc["CN2", "best_score_board"]
