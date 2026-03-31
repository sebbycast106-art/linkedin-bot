"""
tests/test_daily_brief_service.py — Unit tests for daily_brief_service.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app(job_id, status, days_ago, company="Acme", title="Analyst"):
    now = datetime.now(timezone.utc)
    return {
        "job_id": job_id,
        "company": company,
        "title": title,
        "url": "",
        "applied_at": (now - timedelta(days=days_ago)).isoformat(),
        "status": status,
        "follow_up_sent": False,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_empty_apps_sends_brief():
    """Daily brief runs with no apps — returns zeroes."""
    with patch("daily_brief_service._load_applications", return_value=[]), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    assert result["new_jobs"] == 0
    assert result["awaiting"] == 0
    assert result["ghosts"] == 0
    assert result["interviews"] == 0
    mock_tg.send_telegram.assert_called_once()


def test_new_jobs_counted_within_24h():
    """Apps applied in the last 24h appear in new_jobs count."""
    apps = [
        _make_app("j1", "applied", days_ago=0),   # today
        _make_app("j2", "applied", days_ago=0),   # today
        _make_app("j3", "applied", days_ago=2),   # 2 days ago — not new
    ]
    with patch("daily_brief_service._load_applications", return_value=apps), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 75, "week_num": 2}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    assert result["new_jobs"] == 2


def test_ghosts_counted_correctly():
    """Apps applied 14+ days ago with 'applied' status are ghosts."""
    apps = [
        _make_app("j1", "applied", days_ago=20),   # ghost
        _make_app("j2", "applied", days_ago=14),   # ghost (exactly 14)
        _make_app("j3", "applied", days_ago=5),    # not ghost
        _make_app("j4", "interview", days_ago=20), # wrong status
    ]
    with patch("daily_brief_service._load_applications", return_value=apps), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    assert result["ghosts"] == 2


def test_interviews_counted():
    """Apps with status 'interview' are counted."""
    apps = [
        _make_app("j1", "interview", days_ago=5, company="Citadel"),
        _make_app("j2", "interview", days_ago=10, company="Jane Street"),
        _make_app("j3", "applied", days_ago=3),
    ]
    with patch("daily_brief_service._load_applications", return_value=apps), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    assert result["interviews"] == 2


def test_awaiting_counts_all_applied():
    """All apps with status 'applied' contribute to awaiting count."""
    apps = [
        _make_app("j1", "applied", days_ago=1),
        _make_app("j2", "applied", days_ago=20),
        _make_app("j3", "rejected", days_ago=5),
    ]
    with patch("daily_brief_service._load_applications", return_value=apps), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    assert result["awaiting"] == 2


def test_warmup_info_included_in_telegram_block():
    """Warmup capacity line is passed to block."""
    with patch("daily_brief_service._load_applications", return_value=[]), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 50, "week_num": 1}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        run_daily_brief()
    call_args = mock_tg.block.call_args
    rows = call_args[0][1]
    row_dict = dict(rows)
    assert "50%" in row_dict["BOT CAPACITY"]
    assert "Week 1" in row_dict["BOT CAPACITY"]


def test_warmup_failure_falls_back_gracefully():
    """If warmup_service raises, daily brief still runs with fallback value."""
    with patch("daily_brief_service._load_applications", return_value=[]), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", side_effect=Exception("warmup error")):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    assert result is not None
    mock_tg.send_telegram.assert_called_once()


def test_app_missing_applied_at_skipped():
    """Apps with no applied_at field are skipped gracefully."""
    apps = [
        {
            "job_id": "x1",
            "company": "Unknown",
            "title": "Role",
            "status": "applied",
            "applied_at": None,
        }
    ]
    with patch("daily_brief_service._load_applications", return_value=apps), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        result = run_daily_brief()
    # awaiting still counts the app (any applied), but new_jobs and ghosts skip it
    assert result["awaiting"] == 1
    assert result["new_jobs"] == 0


def test_block_title_is_daily_brief():
    """Telegram block title is DAILY BRIEF."""
    with patch("daily_brief_service._load_applications", return_value=[]), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        run_daily_brief()
    call_args = mock_tg.block.call_args
    title = call_args[0][0]
    assert title == "DAILY BRIEF"


def test_block_rows_include_date():
    """Block rows include a DATE field."""
    with patch("daily_brief_service._load_applications", return_value=[]), \
         patch("daily_brief_service.tg") as mock_tg, \
         patch("warmup_service.get_warmup_info", return_value={"pct": 100, "week_num": 3}):
        mock_tg.block.return_value = "<pre>BRIEF</pre>"
        from daily_brief_service import run_daily_brief
        run_daily_brief()
    call_args = mock_tg.block.call_args
    rows = call_args[0][1]
    row_dict = dict(rows)
    assert "DATE" in row_dict
