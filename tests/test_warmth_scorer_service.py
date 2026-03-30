import pytest
from unittest.mock import patch, MagicMock


def test_record_signal_new_profile():
    from warmth_scorer_service import record_signal, get_warmth
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {}}
        record_signal("john-doe", "John Doe", "connection_accepted")

        mock_db.save_state.assert_called_once()
        saved = mock_db.save_state.call_args[0][1]
        assert "john-doe" in saved["scores"]
        assert saved["scores"]["john-doe"]["score"] == 20
        assert saved["scores"]["john-doe"]["name"] == "John Doe"


def test_record_signal_accumulates():
    from warmth_scorer_service import record_signal
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {
            "john-doe": {
                "name": "John Doe",
                "score": 20,
                "signals": {"connection_accepted": 1},
                "last_updated": "2026-01-01",
            }
        }}
        record_signal("john-doe", "John Doe", "messaged_us")

        saved = mock_db.save_state.call_args[0][1]
        assert saved["scores"]["john-doe"]["score"] == 60  # 20 + 40
        assert saved["scores"]["john-doe"]["signals"]["messaged_us"] == 1
        assert saved["scores"]["john-doe"]["signals"]["connection_accepted"] == 1


def test_record_signal_unknown_signal():
    from warmth_scorer_service import record_signal
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {}}
        record_signal("john-doe", "John Doe", "unknown_signal")
        mock_db.save_state.assert_not_called()


def test_get_warmth_scores_sorted():
    from warmth_scorer_service import get_warmth_scores
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {
            "a": {"name": "Alice", "score": 30, "signals": {}, "last_updated": ""},
            "b": {"name": "Bob", "score": 80, "signals": {}, "last_updated": ""},
            "c": {"name": "Carol", "score": 50, "signals": {}, "last_updated": ""},
        }}
        result = get_warmth_scores()
        assert len(result) == 3
        assert result[0]["name"] == "Bob"
        assert result[1]["name"] == "Carol"
        assert result[2]["name"] == "Alice"


def test_get_warmth_scores_min_score_filter():
    from warmth_scorer_service import get_warmth_scores
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {
            "a": {"name": "Alice", "score": 10, "signals": {}, "last_updated": ""},
            "b": {"name": "Bob", "score": 80, "signals": {}, "last_updated": ""},
        }}
        result = get_warmth_scores(min_score=50)
        assert len(result) == 1
        assert result[0]["name"] == "Bob"


def test_get_warmth_existing():
    from warmth_scorer_service import get_warmth
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {
            "john-doe": {"name": "John", "score": 40, "signals": {"messaged_us": 1}, "last_updated": "2026-01-01"},
        }}
        result = get_warmth("john-doe")
        assert result is not None
        assert result["score"] == 40
        assert result["name"] == "John"


def test_get_warmth_nonexistent():
    from warmth_scorer_service import get_warmth
    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": {}}
        result = get_warmth("nobody")
        assert result is None


def test_record_signal_caps_at_2000():
    from warmth_scorer_service import record_signal
    # Create state with 2000 entries
    scores = {}
    for i in range(2000):
        scores[f"user-{i}"] = {"name": f"User {i}", "score": i, "signals": {}, "last_updated": ""}

    with patch("warmth_scorer_service.database") as mock_db:
        mock_db.load_state.return_value = {"scores": scores}
        record_signal("new-user", "New User", "messaged_us")

        saved = mock_db.save_state.call_args[0][1]
        assert len(saved["scores"]) <= 2000
        # The new user (score 40) should survive; lowest scores should be evicted
        assert "new-user" in saved["scores"]
