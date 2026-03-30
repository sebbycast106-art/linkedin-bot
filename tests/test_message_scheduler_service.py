"""
tests/test_message_scheduler_service.py — Unit tests for message_scheduler_service.
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _write_state(tmp_path, filename, data):
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")


_ET = ZoneInfo("America/New_York")


def test_queue_message_adds_entry():
    """Queuing a message should add an entry to the queue."""
    from message_scheduler_service import queue_message, get_queue

    result = queue_message("johndoe", "John Doe", "Hey John!", "recruiter follow-up")
    assert "John Doe" in result

    queue = get_queue()
    assert len(queue) == 1
    assert queue[0]["profile_id"] == "johndoe"
    assert queue[0]["name"] == "John Doe"
    assert queue[0]["status"] == "pending"


def test_queue_message_with_explicit_send_after(tmp_path):
    """Queuing with an explicit send_after should use that time."""
    from message_scheduler_service import queue_message, get_queue

    # Ensure clean state
    _write_state(tmp_path, "message_queue_state.json", {"queue": []})

    send_time = datetime(2026, 4, 1, 10, 0, tzinfo=_ET)
    queue_message("janedoe", "Jane Doe", "Hi Jane!", "networking", send_after=send_time)

    queue = get_queue()
    pending = [e for e in queue if e["name"] == "Jane Doe"]
    assert len(pending) == 1
    assert "2026-04-01" in pending[0]["send_after"]


def test_run_message_queue_sends_reminder(tmp_path):
    """Due messages should trigger Telegram reminders."""
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_state(tmp_path, "message_queue_state.json", {
        "queue": [{
            "id": "abc123",
            "profile_id": "johndoe",
            "name": "John Doe",
            "message_draft": "Hey John!",
            "reason": "follow-up",
            "status": "pending",
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "send_after": past_time,
        }]
    })

    with patch("message_scheduler_service.send_telegram") as mock_tg:
        from message_scheduler_service import run_message_queue
        result = run_message_queue()

    assert result["reminded"] == 1
    assert result["expired"] == 0
    mock_tg.assert_called_once()
    msg = mock_tg.call_args[0][0]
    assert "John Doe" in msg
    assert "Hey John!" in msg
    assert "linkedin.com/in/johndoe" in msg


def test_run_message_queue_expires_old(tmp_path):
    """Messages pending for 7+ days should be expired."""
    old_queued = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    future_send = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _write_state(tmp_path, "message_queue_state.json", {
        "queue": [{
            "id": "old1",
            "profile_id": "oldperson",
            "name": "Old Person",
            "message_draft": "Hi!",
            "reason": "outreach",
            "status": "pending",
            "queued_at": old_queued,
            "send_after": future_send,
        }]
    })

    with patch("message_scheduler_service.send_telegram") as mock_tg:
        from message_scheduler_service import run_message_queue
        result = run_message_queue()

    assert result["expired"] == 1
    assert result["reminded"] == 0
    mock_tg.assert_not_called()


def test_run_message_queue_skips_already_reminded(tmp_path):
    """Already reminded messages should not be sent again."""
    past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    _write_state(tmp_path, "message_queue_state.json", {
        "queue": [{
            "id": "done1",
            "profile_id": "person",
            "name": "Person",
            "message_draft": "Hi!",
            "reason": "outreach",
            "status": "reminded",
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "send_after": past_time,
        }]
    })

    with patch("message_scheduler_service.send_telegram") as mock_tg:
        from message_scheduler_service import run_message_queue
        result = run_message_queue()

    assert result["reminded"] == 0
    assert result["expired"] == 0
    mock_tg.assert_not_called()


def test_get_queue_returns_all_entries(tmp_path):
    """get_queue should return the full queue list."""
    _write_state(tmp_path, "message_queue_state.json", {
        "queue": [
            {"id": "a", "status": "pending", "name": "A"},
            {"id": "b", "status": "reminded", "name": "B"},
        ]
    })

    from message_scheduler_service import get_queue
    queue = get_queue()
    assert len(queue) == 2


def test_optimal_window_calculation():
    """_next_optimal_window should return a Tue-Thu 9-11 or 13-15 ET time."""
    from message_scheduler_service import _next_optimal_window, _OPTIMAL_DAYS, _OPTIMAL_HOURS

    # Saturday at 10 AM ET — next window should be Tuesday
    saturday = datetime(2026, 3, 28, 10, 0, tzinfo=_ET)  # Saturday
    next_win = _next_optimal_window(saturday)
    assert next_win.weekday() in _OPTIMAL_DAYS
    assert any(s <= next_win.hour < e for s, e in _OPTIMAL_HOURS)


def test_in_optimal_window():
    """_in_optimal_window should return True for valid windows."""
    from message_scheduler_service import _in_optimal_window

    # Tuesday 10 AM ET — should be in window
    tue_10am = datetime(2026, 3, 31, 10, 0, tzinfo=_ET)  # Tuesday
    assert _in_optimal_window(tue_10am) is True

    # Tuesday 6 PM ET — should not be in window
    tue_6pm = datetime(2026, 3, 31, 18, 0, tzinfo=_ET)
    assert _in_optimal_window(tue_6pm) is False

    # Monday 10 AM ET — should not be in window (Monday not optimal)
    mon_10am = datetime(2026, 3, 30, 10, 0, tzinfo=_ET)  # Monday
    assert _in_optimal_window(mon_10am) is False
