"""
tests/test_ghost_detector_service.py — Unit tests for ghost_detector_service.
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ghost_app():
    """An app applied 20 days ago — qualifies as a ghost."""
    now = datetime.now(timezone.utc)
    return {
        "job_id": "gs_001",
        "company": "Goldman Sachs",
        "title": "Analyst Intern",
        "url": "https://linkedin.com/jobs/gs001",
        "applied_at": (now - timedelta(days=20)).isoformat(),
        "status": "applied",
        "follow_up_sent": False,
    }


@pytest.fixture
def fresh_app():
    """An app applied 5 days ago — not a ghost yet."""
    now = datetime.now(timezone.utc)
    return {
        "job_id": "jp_002",
        "company": "JPMorgan",
        "title": "Trading Intern",
        "url": "",
        "applied_at": (now - timedelta(days=5)).isoformat(),
        "status": "applied",
        "follow_up_sent": False,
    }


@pytest.fixture
def interview_app():
    """An app in interview stage — should not be flagged."""
    now = datetime.now(timezone.utc)
    return {
        "job_id": "ms_003",
        "company": "Morgan Stanley",
        "title": "Risk Analyst",
        "url": "",
        "applied_at": (now - timedelta(days=30)).isoformat(),
        "status": "interview",
        "follow_up_sent": True,
    }


@pytest.fixture
def already_alerted_app():
    """A ghost app that has already been alerted."""
    now = datetime.now(timezone.utc)
    return {
        "job_id": "fb_004",
        "company": "Fidelity",
        "title": "Co-op",
        "url": "",
        "applied_at": (now - timedelta(days=15)).isoformat(),
        "status": "applied",
        "follow_up_sent": False,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_apps_returns_zero_ghosts():
    with patch("ghost_detector_service._load_applications", return_value=[]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state") as mock_save, \
         patch("ghost_detector_service.tg") as mock_tg:
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 0
    mock_tg.send_telegram.assert_not_called()


def test_ghost_detected_sends_telegram(ghost_app):
    with patch("ghost_detector_service._load_applications", return_value=[ghost_app]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state") as mock_save, \
         patch("ghost_detector_service.tg") as mock_tg:
        mock_tg.block.return_value = "<pre>GHOST</pre>"
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 1
    mock_tg.send_telegram.assert_called_once()
    mock_tg.block.assert_called_once()
    # Verify the block call includes correct data
    call_args = mock_tg.block.call_args
    assert call_args[0][0] == "GHOST DETECTED"
    rows = call_args[0][1]
    row_dict = dict(rows)
    assert row_dict["COMPANY"] == "Goldman Sachs"
    assert row_dict["ROLE"] == "Analyst Intern"


def test_fresh_app_not_flagged(fresh_app):
    with patch("ghost_detector_service._load_applications", return_value=[fresh_app]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state"), \
         patch("ghost_detector_service.tg") as mock_tg:
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 0
    mock_tg.send_telegram.assert_not_called()


def test_interview_app_not_flagged(interview_app):
    with patch("ghost_detector_service._load_applications", return_value=[interview_app]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state"), \
         patch("ghost_detector_service.tg") as mock_tg:
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 0
    mock_tg.send_telegram.assert_not_called()


def test_already_alerted_app_skipped(already_alerted_app):
    with patch("ghost_detector_service._load_applications", return_value=[already_alerted_app]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": ["fb_004"], "last_run": None}), \
         patch("ghost_detector_service.save_state"), \
         patch("ghost_detector_service.tg") as mock_tg:
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 0
    mock_tg.send_telegram.assert_not_called()


def test_alerted_ids_saved_after_detection(ghost_app):
    saved_state = {}
    def capture_save(filename, state):
        saved_state.update(state)

    with patch("ghost_detector_service._load_applications", return_value=[ghost_app]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state", side_effect=capture_save), \
         patch("ghost_detector_service.tg") as mock_tg:
        mock_tg.block.return_value = "<pre>GHOST</pre>"
        from ghost_detector_service import run_ghost_detector
        run_ghost_detector()
    assert "gs_001" in saved_state["alerted_ids"]
    assert saved_state["last_run"] is not None


def test_multiple_ghosts(ghost_app):
    now = datetime.now(timezone.utc)
    ghost2 = {
        "job_id": "br_005",
        "company": "BlackRock",
        "title": "PM Intern",
        "url": "",
        "applied_at": (now - timedelta(days=25)).isoformat(),
        "status": "applied",
        "follow_up_sent": False,
    }
    with patch("ghost_detector_service._load_applications", return_value=[ghost_app, ghost2]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state"), \
         patch("ghost_detector_service.tg") as mock_tg:
        mock_tg.block.return_value = "<pre>GHOST</pre>"
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 2
    assert mock_tg.send_telegram.call_count == 2


def test_app_with_no_applied_at_skipped():
    app_no_date = {
        "job_id": "x_999",
        "company": "Unknown",
        "title": "Unknown",
        "url": "",
        "applied_at": None,
        "status": "applied",
    }
    with patch("ghost_detector_service._load_applications", return_value=[app_no_date]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state"), \
         patch("ghost_detector_service.tg") as mock_tg:
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 0


def test_app_with_invalid_applied_at_skipped():
    app_bad_date = {
        "job_id": "x_888",
        "company": "Weird Co",
        "title": "Weird Role",
        "url": "",
        "applied_at": "not-a-date",
        "status": "applied",
    }
    with patch("ghost_detector_service._load_applications", return_value=[app_bad_date]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": [], "last_run": None}), \
         patch("ghost_detector_service.save_state"), \
         patch("ghost_detector_service.tg") as mock_tg:
        from ghost_detector_service import run_ghost_detector
        result = run_ghost_detector()
    assert result["ghosts_found"] == 0


def test_get_ghost_count():
    now = datetime.now(timezone.utc)
    apps = [
        {"job_id": "a1", "status": "applied", "applied_at": (now - timedelta(days=20)).isoformat()},  # ghost
        {"job_id": "a2", "status": "applied", "applied_at": (now - timedelta(days=5)).isoformat()},   # not ghost
        {"job_id": "a3", "status": "interview", "applied_at": (now - timedelta(days=20)).isoformat()}, # wrong status
        {"job_id": "a4", "status": "applied", "applied_at": (now - timedelta(days=14)).isoformat()},  # exactly 14 = ghost
    ]
    with patch("ghost_detector_service._load_applications", return_value=apps):
        from ghost_detector_service import get_ghost_count
        count = get_ghost_count()
    assert count == 2


def test_alerted_ids_capped_at_2000(ghost_app):
    # Pre-fill alerted_ids with 1999 entries
    existing_ids = [f"old_{i}" for i in range(1999)]
    saved_state = {}

    def capture_save(filename, state):
        saved_state.update(state)

    with patch("ghost_detector_service._load_applications", return_value=[ghost_app]), \
         patch("ghost_detector_service.load_state", return_value={"alerted_ids": existing_ids, "last_run": None}), \
         patch("ghost_detector_service.save_state", side_effect=capture_save), \
         patch("ghost_detector_service.tg") as mock_tg:
        mock_tg.block.return_value = "<pre>GHOST</pre>"
        from ghost_detector_service import run_ghost_detector
        run_ghost_detector()
    assert len(saved_state["alerted_ids"]) == 2000
