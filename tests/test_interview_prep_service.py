"""
tests/test_interview_prep_service.py — Unit tests for interview_prep_service.
"""
import pytest
from unittest.mock import MagicMock, patch

import interview_prep_service


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# Test 1: generate_prep_package returns a non-empty string on success
# ---------------------------------------------------------------------------

def test_generate_prep_package_returns_string():
    """Mock Claude; assert a non-empty string is returned."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text="🎯 Interview Questions\n1. Tell me about yourself...\n")
    ]
    mock_client.messages.create.return_value = mock_response

    with patch("interview_prep_service.anthropic.Anthropic", return_value=mock_client):
        result = interview_prep_service.generate_prep_package("Analyst", "Fidelity")

    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Test 2: generate_prep_package returns a fallback string when Claude raises
# ---------------------------------------------------------------------------

def test_generate_prep_package_fallback_on_error():
    """When Claude raises an exception, a fallback string (not None) is returned."""
    with patch(
        "interview_prep_service.anthropic.Anthropic",
        side_effect=Exception("API error"),
    ):
        result = interview_prep_service.generate_prep_package("Analyst", "Goldman Sachs")

    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# Test 3: run_interview_prep_check skips already-prepped job_ids
# ---------------------------------------------------------------------------

def test_run_interview_prep_check_skips_already_prepped(tmp_path, monkeypatch):
    """An interview app whose job_id is already in prepped_ids → count=0, send_telegram not called."""
    apps = [
        {
            "job_id": "job-001",
            "company": "Stripe",
            "title": "Finance Intern",
            "status": "interview",
            "applied_at": "2026-03-01T00:00:00+00:00",
            "follow_up_sent": False,
        }
    ]
    existing_state = {"prepped_ids": ["job-001"]}

    with patch("interview_prep_service.application_tracker.get_applications", return_value=apps), \
         patch("interview_prep_service.database.load_state", return_value=existing_state), \
         patch("interview_prep_service.database.save_state") as mock_save, \
         patch("interview_prep_service.send_telegram") as mock_telegram:

        result = interview_prep_service.run_interview_prep_check()

    assert result == {"prepped": 0}
    mock_telegram.assert_not_called()
    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: run_interview_prep_check sends prep for new interview apps
# ---------------------------------------------------------------------------

def test_run_interview_prep_check_sends_prep(tmp_path, monkeypatch):
    """An interview app not yet in prepped_ids → send_telegram called, count=1, job_id added."""
    apps = [
        {
            "job_id": "job-002",
            "company": "Robinhood",
            "title": "Fintech Co-op",
            "status": "interview",
            "applied_at": "2026-03-10T00:00:00+00:00",
            "follow_up_sent": False,
        }
    ]
    initial_state = {"prepped_ids": []}
    saved_states = []

    def _save(filename, data):
        saved_states.append(data)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="📋 Prep package content here")]
    mock_client.messages.create.return_value = mock_response

    with patch("interview_prep_service.application_tracker.get_applications", return_value=apps), \
         patch("interview_prep_service.database.load_state", return_value=initial_state), \
         patch("interview_prep_service.database.save_state", side_effect=_save), \
         patch("interview_prep_service.send_telegram") as mock_telegram, \
         patch("interview_prep_service.anthropic.Anthropic", return_value=mock_client):

        result = interview_prep_service.run_interview_prep_check()

    assert result == {"prepped": 1}
    mock_telegram.assert_called_once()
    assert len(saved_states) == 1
    assert "job-002" in saved_states[0]["prepped_ids"]


# ---------------------------------------------------------------------------
# Test 5: run_interview_prep_check ignores non-interview statuses
# ---------------------------------------------------------------------------

def test_run_interview_prep_check_ignores_non_interview(tmp_path, monkeypatch):
    """Apps with status=applied or seen are not returned by get_applications(status_filter='interview') → count=0."""
    # get_applications with status_filter="interview" would return [] for applied/seen apps
    with patch("interview_prep_service.application_tracker.get_applications", return_value=[]), \
         patch("interview_prep_service.database.load_state", return_value={"prepped_ids": []}), \
         patch("interview_prep_service.database.save_state") as mock_save, \
         patch("interview_prep_service.send_telegram") as mock_telegram:

        result = interview_prep_service.run_interview_prep_check()

    assert result == {"prepped": 0}
    mock_telegram.assert_not_called()
    mock_save.assert_not_called()
