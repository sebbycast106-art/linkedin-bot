import pytest
from unittest.mock import patch, MagicMock, call


def _make_state(buffer=None, last_flush=""):
    return {
        "buffer": buffer if buffer is not None else [],
        "last_flush": last_flush,
    }


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_flush_empty_buffer(mock_tg, mock_db):
    mock_db.load_state.return_value = _make_state()
    from notification_service import flush_notifications
    result = flush_notifications()
    assert result["sent"] == 0
    mock_tg.assert_not_called()


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_flush_with_items(mock_tg, mock_db):
    mock_db.load_state.return_value = _make_state(buffer=[
        {"category": "jobs", "message": "New job found", "priority": "normal", "timestamp": "2026-01-01T00:00:00+00:00"},
        {"category": "networking", "message": "Connection accepted", "priority": "normal", "timestamp": "2026-01-01T00:00:00+00:00"},
    ])
    from notification_service import flush_notifications
    result = flush_notifications()
    assert result["sent"] == 2
    mock_tg.assert_called_once()
    msg = mock_tg.call_args[0][0]
    assert "Jobs" in msg
    assert "Networking" in msg
    # Buffer should be cleared
    saved = mock_db.save_state.call_args[0][1]
    assert saved["buffer"] == []
    assert saved["last_flush"] != ""


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_buffer_notification(mock_tg, mock_db):
    mock_db.load_state.return_value = _make_state()
    from notification_service import buffer_notification
    buffer_notification("jobs", "Test message")
    mock_db.save_state.assert_called_once()
    saved = mock_db.save_state.call_args[0][1]
    assert len(saved["buffer"]) == 1
    assert saved["buffer"][0]["category"] == "jobs"
    assert saved["buffer"][0]["message"] == "Test message"
    mock_tg.assert_not_called()


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_send_or_buffer_high_priority(mock_tg, mock_db):
    from notification_service import send_or_buffer
    send_or_buffer("system", "Urgent message", priority="high")
    mock_tg.assert_called_once_with("Urgent message")


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_send_or_buffer_immediate(mock_tg, mock_db):
    from notification_service import send_or_buffer
    send_or_buffer("jobs", "Important job", immediate=True)
    mock_tg.assert_called_once_with("Important job")


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_send_or_buffer_normal(mock_tg, mock_db):
    mock_db.load_state.return_value = _make_state()
    from notification_service import send_or_buffer
    send_or_buffer("jobs", "Normal message")
    # Should buffer, not send immediately
    mock_db.save_state.assert_called_once()


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_invalid_category_defaults_to_system(mock_tg, mock_db):
    mock_db.load_state.return_value = _make_state()
    from notification_service import buffer_notification
    buffer_notification("invalid_category", "Test")
    saved = mock_db.save_state.call_args[0][1]
    assert saved["buffer"][0]["category"] == "system"


@patch("notification_service.database")
@patch("notification_service.send_telegram")
def test_auto_flush_on_cap(mock_tg, mock_db):
    # Create a buffer at cap-1, adding one more should trigger auto-flush
    existing = [
        {"category": "jobs", "message": f"msg_{i}", "priority": "normal", "timestamp": "2026-01-01T00:00:00+00:00"}
        for i in range(49)
    ]
    # First load returns buffer at 49, second load (during flush) returns the 50-item buffer
    mock_db.load_state.side_effect = [
        _make_state(buffer=existing),
        _make_state(buffer=existing + [{"category": "jobs", "message": "msg_49", "priority": "normal", "timestamp": "2026-01-01T00:00:00+00:00"}]),
    ]
    from notification_service import buffer_notification
    buffer_notification("jobs", "Trigger flush")
    # send_telegram should have been called for the auto-flush
    assert mock_tg.call_count >= 1
