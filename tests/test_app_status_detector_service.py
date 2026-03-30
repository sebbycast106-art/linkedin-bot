"""
tests/test_app_status_detector_service.py — Unit tests for app_status_detector_service.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _write_state(tmp_path, filename, data):
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_app(job_id, company, title, status="applied", days_ago=0):
    applied_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {
        "job_id": job_id,
        "company": company,
        "title": title,
        "url": f"https://linkedin.com/jobs/{job_id}",
        "applied_at": applied_at,
        "status": status,
        "follow_up_sent": False,
    }


def test_no_stale_apps_returns_zero(tmp_path):
    """Fresh applications should not trigger any suggestions."""
    apps = [_make_app("j1", "Goldman", "Analyst", days_ago=1)]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 0
    assert result["suggested"] == 0
    mock_tg.assert_not_called()


def test_stale_app_triggers_suggestion(tmp_path):
    """An app applied 5 days ago should trigger a Telegram reminder."""
    apps = [_make_app("j1", "Citadel", "Quant Intern", days_ago=5)]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 1
    assert result["suggested"] == 1
    mock_tg.assert_called_once()
    msg = mock_tg.call_args[0][0]
    assert "Citadel" in msg
    assert "Quant Intern" in msg
    assert "/update j1" in msg


def test_dedup_no_spam(tmp_path):
    """Once an app has been suggested, it should not be suggested again."""
    apps = [_make_app("j1", "Citadel", "Quant Intern", days_ago=5)]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})
    # Pre-populate state with already-suggested job_id
    _write_state(tmp_path, "status_detector_state.json", {
        "last_run": "",
        "suggested_updates": ["j1"],
    })

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 0
    assert result["suggested"] == 0
    mock_tg.assert_not_called()


def test_batch_limit(tmp_path):
    """At most 10 apps should be processed per run."""
    apps = [_make_app(f"j{i}", f"Company{i}", f"Title{i}", days_ago=5) for i in range(15)]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 10
    assert result["suggested"] == 10
    assert mock_tg.call_count == 10


def test_non_applied_apps_ignored(tmp_path):
    """Apps with status other than 'applied' should not trigger suggestions."""
    apps = [
        _make_app("j1", "Goldman", "Analyst", status="interview", days_ago=10),
        _make_app("j2", "JPMorgan", "Intern", status="rejected", days_ago=10),
        _make_app("j3", "BlackRock", "Dev", status="seen", days_ago=10),
    ]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 0
    assert result["suggested"] == 0
    mock_tg.assert_not_called()


def test_state_persistence(tmp_path):
    """Suggested job_ids should be persisted in state file."""
    apps = [_make_app("j1", "Stripe", "SWE Intern", days_ago=4)]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})

    with patch("app_status_detector_service.send_telegram"):
        from app_status_detector_service import run_status_detection
        run_status_detection()

    import database
    state = database.load_state("status_detector_state.json", default={})
    assert "j1" in state["suggested_updates"]
    assert state["last_run"] != ""


def test_empty_tracker(tmp_path):
    """Empty application tracker should return zeros gracefully."""
    _write_state(tmp_path, "application_tracker_state.json", {"applications": []})

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 0
    assert result["suggested"] == 0
    mock_tg.assert_not_called()


def test_prioritizes_oldest_first(tmp_path):
    """Oldest stale apps should be processed first."""
    apps = [
        _make_app("j_new", "NewCo", "New Role", days_ago=4),
        _make_app("j_old", "OldCo", "Old Role", days_ago=20),
    ]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": apps})

    with patch("app_status_detector_service.send_telegram") as mock_tg:
        from app_status_detector_service import run_status_detection
        result = run_status_detection()

    assert result["detected"] == 2
    # First call should be for the oldest app
    first_msg = mock_tg.call_args_list[0][0][0]
    assert "OldCo" in first_msg
