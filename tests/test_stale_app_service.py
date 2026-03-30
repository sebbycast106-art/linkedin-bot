import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


@pytest.fixture
def empty_apps():
    return []


@pytest.fixture
def stale_apps():
    now = datetime.now(timezone.utc)
    return [
        {
            "job_id": "gs_001",
            "company": "Goldman Sachs",
            "title": "Analyst Intern",
            "url": "",
            "applied_at": (now - timedelta(days=30)).isoformat(),
            "status": "applied",
            "follow_up_sent": True,
        },
        {
            "job_id": "jp_002",
            "company": "JPMorgan",
            "title": "Trading Intern",
            "url": "",
            "applied_at": (now - timedelta(days=25)).isoformat(),
            "status": "applied",
            "follow_up_sent": True,
        },
    ]


@pytest.fixture
def fresh_apps():
    now = datetime.now(timezone.utc)
    return [
        {
            "job_id": "ms_003",
            "company": "Morgan Stanley",
            "title": "Risk Analyst",
            "url": "",
            "applied_at": (now - timedelta(days=5)).isoformat(),
            "status": "applied",
            "follow_up_sent": True,
        },
    ]


@pytest.fixture
def no_followup_apps():
    now = datetime.now(timezone.utc)
    return [
        {
            "job_id": "fb_004",
            "company": "Fidelity",
            "title": "Co-op",
            "url": "",
            "applied_at": (now - timedelta(days=30)).isoformat(),
            "status": "applied",
            "follow_up_sent": False,
        },
    ]


def test_no_stale_apps(empty_apps):
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = empty_apps
        from stale_app_service import run_stale_check
        result = run_stale_check()
    assert result["stale_count"] == 0
    assert result["notified"] is False
    mock_tg.assert_not_called()


def test_stale_apps_notified(stale_apps):
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = stale_apps
        from stale_app_service import run_stale_check
        result = run_stale_check()
    assert result["stale_count"] == 2
    assert result["notified"] is True
    mock_tg.assert_called_once()
    msg = mock_tg.call_args[0][0]
    assert "Goldman Sachs" in msg
    assert "JPMorgan" in msg


def test_fresh_apps_not_stale(fresh_apps):
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = fresh_apps
        from stale_app_service import run_stale_check
        result = run_stale_check()
    assert result["stale_count"] == 0
    assert result["notified"] is False
    mock_tg.assert_not_called()


def test_no_followup_not_stale(no_followup_apps):
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = no_followup_apps
        from stale_app_service import run_stale_check
        result = run_stale_check()
    assert result["stale_count"] == 0
    assert result["notified"] is False


def test_custom_stale_days(stale_apps):
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = stale_apps
        from stale_app_service import run_stale_check
        # With stale_days=50, the 30-day-old apps should not be stale
        result = run_stale_check(stale_days=50)
    assert result["stale_count"] == 0
    assert result["notified"] is False


def test_message_suggests_archive(stale_apps):
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = stale_apps
        from stale_app_service import run_stale_check
        run_stale_check()
    msg = mock_tg.call_args[0][0]
    assert "archived" in msg.lower() or "/update" in msg


def test_mixed_apps(stale_apps, fresh_apps):
    combined = stale_apps + fresh_apps
    with patch("stale_app_service.application_tracker") as mock_tracker, \
         patch("stale_app_service.send_telegram") as mock_tg:
        mock_tracker.get_applications.return_value = combined
        from stale_app_service import run_stale_check
        result = run_stale_check()
    assert result["stale_count"] == 2
    assert result["notified"] is True
