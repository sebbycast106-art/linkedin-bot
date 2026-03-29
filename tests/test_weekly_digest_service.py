"""
tests/test_weekly_digest_service.py — Unit tests for weekly_digest_service.
"""
import json
import os
import pytest
from unittest.mock import patch

import weekly_digest_service


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# Test 1: runs without error on empty state
# ---------------------------------------------------------------------------

def test_digest_runs_with_empty_state():
    with patch("weekly_digest_service.send_telegram"):
        result = weekly_digest_service.run_weekly_digest()
    assert isinstance(result, str)
    assert "Weekly" in result


# ---------------------------------------------------------------------------
# Test 2: calculates deltas correctly
# ---------------------------------------------------------------------------

def test_digest_calculates_deltas(tmp_path):
    # Save a prior snapshot with 10 connections
    snapshot = {
        "snapshot_date": "2026-03-22",
        "total_connections": 10,
        "total_applied": 0,
        "total_seen_jobs": 0,
        "total_recruiter_sent": 0,
        "total_recruiter_messaged": 0,
        "total_easy_applied": 0,
    }
    snapshot_path = tmp_path / "digest_state.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")

    # Set connector_state with 15 connected_ids
    connector_state = {
        "date": "2026-03-29",
        "connects_today": 5,
        "connected_ids": [f"id{i}" for i in range(15)],
    }
    connector_path = tmp_path / "connector_state.json"
    connector_path.write_text(json.dumps(connector_state), encoding="utf-8")

    with patch("weekly_digest_service.send_telegram"):
        result = weekly_digest_service.run_weekly_digest()

    assert "+5" in result


# ---------------------------------------------------------------------------
# Test 3: saves snapshot after running
# ---------------------------------------------------------------------------

def test_digest_saves_snapshot(tmp_path):
    with patch("weekly_digest_service.send_telegram"):
        weekly_digest_service.run_weekly_digest()

    snapshot_path = tmp_path / "digest_state.json"
    assert snapshot_path.exists(), "digest_state.json should be created after digest"

    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert "total_connections" in data


# ---------------------------------------------------------------------------
# Test 4: shows top companies
# ---------------------------------------------------------------------------

def test_digest_shows_top_companies(tmp_path):
    applications = (
        [{"job_id": f"br{i}", "company": "BlackRock", "title": "Intern", "status": "applied", "applied_at": "2026-03-29T00:00:00", "follow_up_sent": False} for i in range(3)]
        + [{"job_id": f"cit{i}", "company": "Citadel", "title": "Analyst", "status": "applied", "applied_at": "2026-03-29T00:00:00", "follow_up_sent": False} for i in range(2)]
    )
    tracker_state = {"applications": applications}
    tracker_path = tmp_path / "application_tracker_state.json"
    tracker_path.write_text(json.dumps(tracker_state), encoding="utf-8")

    with patch("weekly_digest_service.send_telegram"):
        result = weekly_digest_service.run_weekly_digest()

    assert "BlackRock" in result


# ---------------------------------------------------------------------------
# Test 5: calls send_telegram once
# ---------------------------------------------------------------------------

def test_digest_sends_telegram():
    with patch("weekly_digest_service.send_telegram") as mock_send:
        weekly_digest_service.run_weekly_digest()

    mock_send.assert_called_once()
