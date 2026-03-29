"""
tests/test_health_service.py — Unit tests for health_service.get_status().
"""
import pytest
import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import health_service
import database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _write_state(tmp_path, filename, data):
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# Test 1: empty state — all numerics default to 0
# ---------------------------------------------------------------------------

def test_get_status_empty_state():
    status = health_service.get_status()

    assert "today" in status
    assert isinstance(status["today"], str) and len(status["today"]) == 10

    # Check that every leaf numeric value is an int >= 0
    def _check_numerics(d):
        for v in d.values():
            if isinstance(v, dict):
                _check_numerics(v)
            elif isinstance(v, int):
                assert v >= 0

    _check_numerics(status)

    # Spot-check specific zero values
    assert status["connections"]["sent_today"] == 0
    assert status["connections"]["total_all_time"] == 0
    assert status["recruiter"]["sent_today"] == 0
    assert status["recruiter"]["pending_followup"] == 0
    assert status["profile_views"]["sent_today"] == 0
    assert status["engagement"]["likes_today"] == 0
    assert status["engagement"]["comments_today"] == 0
    assert status["jobs"]["total_seen"] == 0
    assert status["jobs"]["total_easy_applied"] == 0
    assert status["applications"]["total"] == 0
    assert status["applications"]["pending_followup"] == 0
    assert status["inbox"]["seen_threads"] == 0


# ---------------------------------------------------------------------------
# Test 2: connections state
# ---------------------------------------------------------------------------

def test_get_status_connections(tmp_path):
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    connected_ids = [f"id{i}" for i in range(20)]
    _write_state(tmp_path, "connector_state.json", {
        "date": today,
        "connects_today": 5,
        "connected_ids": connected_ids,
    })

    status = health_service.get_status()

    assert status["connections"]["sent_today"] == 5
    assert status["connections"]["total_all_time"] == 20
    assert status["connections"]["daily_limit"] == 20


# ---------------------------------------------------------------------------
# Test 3: applications by_status counts
# ---------------------------------------------------------------------------

def test_get_status_applications_by_status(tmp_path):
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    applications = [
        {"job_id": f"j{i}", "company": "Co", "title": "Analyst",
         "status": "applied", "applied_at": today + "T12:00:00", "follow_up_sent": True}
        for i in range(3)
    ] + [
        {"job_id": "j_int", "company": "Co", "title": "Analyst",
         "status": "interview", "applied_at": today + "T12:00:00", "follow_up_sent": False}
    ]

    _write_state(tmp_path, "application_tracker_state.json", {"applications": applications})

    status = health_service.get_status()

    assert status["applications"]["by_status"]["applied"] == 3
    assert status["applications"]["by_status"]["interview"] == 1
    assert status["applications"]["total"] == 4


# ---------------------------------------------------------------------------
# Test 4: pending_followup logic (applied, not sent, older than 5 days)
# ---------------------------------------------------------------------------

def test_get_status_pending_followup(tmp_path):
    old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()

    applications = [
        {
            "job_id": "j1",
            "company": "Acme",
            "title": "Analyst",
            "status": "applied",
            "applied_at": old_date,
            "follow_up_sent": False,
        }
    ]
    _write_state(tmp_path, "application_tracker_state.json", {"applications": applications})

    status = health_service.get_status()

    assert status["applications"]["pending_followup"] == 1


# ---------------------------------------------------------------------------
# Test 5: engagement state
# ---------------------------------------------------------------------------

def test_get_status_engagement(tmp_path):
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    _write_state(tmp_path, "engagement_state.json", {
        "date": today,
        "likes": 30,
        "comments": 10,
    })

    status = health_service.get_status()

    assert status["engagement"]["likes_today"] == 30
    assert status["engagement"]["comments_today"] == 10
    assert status["engagement"]["likes_limit"] == 50
    assert status["engagement"]["comments_limit"] == 20


# ---------------------------------------------------------------------------
# Test 6: error handling — load_state raises an exception
# ---------------------------------------------------------------------------

def test_get_status_returns_error_on_exception(monkeypatch):
    def _explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(database, "load_state", _explode)
    # Also patch the reference used inside health_service
    with patch("health_service.database.load_state", side_effect=RuntimeError("disk full")):
        result = health_service.get_status()

    assert "error" in result
    assert "disk full" in result["error"]
