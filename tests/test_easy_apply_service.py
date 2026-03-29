"""
tests/test_easy_apply_service.py — Unit tests for easy_apply_service.
"""
import json
import os
import pytest
from unittest.mock import MagicMock, patch

import easy_apply_service


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


# ---------------------------------------------------------------------------
# Test 1: No Easy Apply button — returns False
# ---------------------------------------------------------------------------

def test_try_easy_apply_no_button():
    """When no Easy Apply button is found, try_easy_apply returns False."""
    page = MagicMock()
    page.query_selector.return_value = None

    with patch("easy_apply_service.random_delay"):
        result = easy_apply_service.try_easy_apply(page, "https://www.linkedin.com/jobs/view/123/")

    assert result is False


# ---------------------------------------------------------------------------
# Test 2: Complex form (>2 sections) — dismissed and returns False
# ---------------------------------------------------------------------------

def test_try_easy_apply_complex_form_skipped():
    """When form has more than 2 sections, it is treated as complex and skipped."""
    page = MagicMock()

    easy_apply_btn = MagicMock()
    dismiss_btn = MagicMock()

    def _query_selector(selector):
        if "Easy Apply" in selector:
            return easy_apply_btn
        if "Dismiss" in selector:
            return dismiss_btn
        return None

    page.query_selector.side_effect = _query_selector
    # Return 3 form sections — triggers complex form path
    page.query_selector_all.return_value = [MagicMock(), MagicMock(), MagicMock()]

    with patch("easy_apply_service.random_delay"):
        result = easy_apply_service.try_easy_apply(page, "https://www.linkedin.com/jobs/view/456/")

    assert result is False
    dismiss_btn.click.assert_called()


# ---------------------------------------------------------------------------
# Test 3: Simple form with submit button — success element found, returns True
# ---------------------------------------------------------------------------

def test_try_easy_apply_success():
    """Simple single-step form with success indicator returns True."""
    page = MagicMock()

    easy_apply_btn = MagicMock()
    submit_btn = MagicMock()
    success_el = MagicMock()
    phone_input = MagicMock()
    phone_input.input_value.return_value = ""

    def _query_selector(selector):
        if "Easy Apply" in selector:
            return easy_apply_btn
        if "Submit application" in selector:
            return submit_btn
        if ".artdeco-inline-feedback--success" in selector:
            return success_el
        if "phoneNumber" in selector or "type='tel'" in selector or 'type="tel"' in selector:
            return phone_input
        if "Review" in selector:
            return None
        if "file" in selector:
            return None
        if "Dismiss" in selector:
            return None
        return None

    page.query_selector.side_effect = _query_selector
    # 1 form section — simple form
    page.query_selector_all.return_value = [MagicMock()]
    page.url = "https://www.linkedin.com/jobs/view/789/"

    with patch("easy_apply_service.random_delay"):
        result = easy_apply_service.try_easy_apply(page, "https://www.linkedin.com/jobs/view/789/")

    assert result is True
    submit_btn.click.assert_called()


# ---------------------------------------------------------------------------
# Test 4: Batch respects daily limit of 5
# ---------------------------------------------------------------------------

def test_run_easy_apply_batch_respects_limit():
    """Only 5 jobs are attempted regardless of how many are provided."""
    jobs = [
        {"job_id": f"j{i}", "company": "ACME", "title": "Engineer", "url": f"https://li.com/jobs/{i}"}
        for i in range(10)
    ]

    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page

    attempt_count = 0

    def fake_try_easy_apply(page, url):
        nonlocal attempt_count
        attempt_count += 1
        return False  # always skip

    with patch("easy_apply_service.try_easy_apply", side_effect=fake_try_easy_apply), \
         patch("easy_apply_service.random_delay"), \
         patch("easy_apply_service.add_application"):
        result = easy_apply_service.run_easy_apply_batch(mock_session, jobs)

    assert attempt_count == 5
    assert result["skipped"] == 5  # remaining 5 over-limit jobs skipped
    assert result["applied"] == 0


# ---------------------------------------------------------------------------
# Test 5: Already-applied jobs are skipped
# ---------------------------------------------------------------------------

def test_run_easy_apply_batch_skips_already_applied(tmp_path, monkeypatch):
    """Jobs whose job_id is already in applied_ids are skipped without calling try_easy_apply."""
    import database

    # Pre-populate state with j1 already applied
    state = {"applied_ids": ["j1"]}
    database.save_state("easy_apply_state.json", state)

    jobs = [
        {"job_id": "j1", "company": "ACME", "title": "Engineer", "url": "https://li.com/jobs/j1"},
        {"job_id": "j2", "company": "ACME", "title": "Engineer", "url": "https://li.com/jobs/j2"},
    ]

    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page

    attempted_urls = []

    def fake_try_easy_apply(page, url):
        attempted_urls.append(url)
        return False

    with patch("easy_apply_service.try_easy_apply", side_effect=fake_try_easy_apply), \
         patch("easy_apply_service.random_delay"), \
         patch("easy_apply_service.add_application"):
        result = easy_apply_service.run_easy_apply_batch(mock_session, jobs)

    # j1 should not have been attempted
    assert "https://li.com/jobs/j1" not in attempted_urls
    # j2 should have been attempted
    assert "https://li.com/jobs/j2" in attempted_urls
    assert result["skipped"] >= 1


# ---------------------------------------------------------------------------
# Test 6: Successful apply tracked in state and add_application called
# ---------------------------------------------------------------------------

def test_run_easy_apply_batch_tracks_applied_job(tmp_path, monkeypatch):
    """When try_easy_apply returns True, job_id is saved to state and add_application called."""
    import database

    jobs = [
        {"job_id": "j99", "company": "Initech", "title": "Dev", "url": "https://li.com/jobs/j99"},
    ]

    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page

    with patch("easy_apply_service.try_easy_apply", return_value=True), \
         patch("easy_apply_service.random_delay"), \
         patch("easy_apply_service.add_application") as mock_add_app:
        result = easy_apply_service.run_easy_apply_batch(mock_session, jobs)

    # add_application should have been called with correct args
    mock_add_app.assert_called_once_with(
        "j99", "Initech", "Dev", "https://li.com/jobs/j99", status="applied"
    )

    # State file should have j99 in applied_ids
    state = database.load_state("easy_apply_state.json", default={"applied_ids": []})
    assert "j99" in state["applied_ids"]

    assert result["applied"] == 1


# ---------------------------------------------------------------------------
# Test 7: Low description score skips apply
# ---------------------------------------------------------------------------

def test_low_description_score_skips_apply():
    """When description score is below 7, try_easy_apply returns False without clicking Easy Apply."""
    page = MagicMock()

    easy_apply_btn = MagicMock()

    def _query_selector(selector):
        if "Easy Apply" in selector:
            return easy_apply_btn
        return None

    page.query_selector.side_effect = _query_selector
    page.query_selector_all.return_value = []

    with patch("easy_apply_service.random_delay"), \
         patch("easy_apply_service.job_scorer.scrape_job_description", return_value="some description"), \
         patch("easy_apply_service.job_scorer.score_job_description", return_value=4):
        result = easy_apply_service.try_easy_apply(page, "https://www.linkedin.com/jobs/view/999/")

    assert result is False
    easy_apply_btn.click.assert_not_called()
