"""
tests/test_alumni_connector_service.py — Unit tests for alumni_connector_service.
"""
import pytest
from unittest.mock import MagicMock, patch

import alumni_connector_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session():
    """Return (mock_session, search_page, profile_page)."""
    mock_session = MagicMock()
    search_page = MagicMock()
    profile_page = MagicMock()
    mock_session.new_page.side_effect = [search_page, profile_page]
    search_page.goto = MagicMock()
    search_page.query_selector_all.return_value = []
    search_page.query_selector.return_value = None
    return mock_session, search_page, profile_page


def _make_result_element(
    name="Jane Lee",
    href="https://www.linkedin.com/in/jane-lee-neu/",
):
    """Build a mock search-result DOM element."""
    mock_result = MagicMock()

    mock_name_el = MagicMock()
    mock_name_el.inner_text.return_value = name

    mock_link_el = MagicMock()
    mock_link_el.get_attribute.return_value = href

    def _result_qs(selector):
        if "title-text" in selector:
            return mock_name_el
        if "/in/" in selector:
            return mock_link_el
        return None

    mock_result.query_selector.side_effect = _result_qs
    return mock_result


# ---------------------------------------------------------------------------
# Test 1: _generate_alumni_message returns a string <= 300 chars
# ---------------------------------------------------------------------------

def test_generate_alumni_message_returns_string():
    """When Claude responds successfully, result is a non-empty string <= 300 chars."""
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hi Jane! Fellow Husky here — would love to connect and hear about your path at Goldman!")]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("alumni_connector_service.anthropic.Anthropic", return_value=mock_client):
        result = alumni_connector_service._generate_alumni_message(
            name="Jane",
            company="Goldman Sachs",
            headline="Analyst at Goldman Sachs",
            school="Northeastern University",
        )

    assert isinstance(result, str)
    assert len(result) > 0
    assert len(result) <= 300


# ---------------------------------------------------------------------------
# Test 2: _generate_alumni_message returns fallback on Claude error
# ---------------------------------------------------------------------------

def test_generate_alumni_message_fallback_on_error():
    """When Claude raises an exception, the hardcoded fallback is returned."""
    with patch("alumni_connector_service.anthropic.Anthropic", side_effect=Exception("API down")):
        result = alumni_connector_service._generate_alumni_message(
            name="Alex",
            company="Citadel",
        )

    assert "Alex" in result
    assert "Citadel" in result
    assert "Northeastern" in result
    assert len(result) <= 300


# ---------------------------------------------------------------------------
# Test 3: run_alumni_connections respects daily limit
# ---------------------------------------------------------------------------

def test_run_alumni_connections_respects_daily_limit(monkeypatch, tmp_path):
    """When sent_today already equals the daily limit, no page.goto is called."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    mock_session, search_page, profile_page = _make_mock_session()

    state_at_limit = {
        "date": today,
        "sent_today": 10,
        "connected_ids": [],
    }

    with patch("alumni_connector_service.database.load_state", return_value=state_at_limit), \
         patch("alumni_connector_service.database.save_state"), \
         patch("alumni_connector_service.random_delay"):

        result = alumni_connector_service.run_alumni_connections(mock_session)

    search_page.goto.assert_not_called()
    assert result["sent"] == 0


# ---------------------------------------------------------------------------
# Test 4: run_alumni_connections skips already-connected profile IDs
# ---------------------------------------------------------------------------

def test_run_alumni_connections_skips_known_ids(monkeypatch, tmp_path):
    """Profiles whose ID is already in connected_ids are skipped without scraping."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    from datetime import datetime
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    mock_session, search_page, profile_page = _make_mock_session()

    known_id = "jane-lee-neu"
    mock_result = _make_result_element(href=f"https://www.linkedin.com/in/{known_id}/")
    search_page.query_selector_all.return_value = [mock_result]

    state_with_known = {
        "date": today,
        "sent_today": 0,
        "connected_ids": [known_id],
    }

    with patch("alumni_connector_service.database.load_state", return_value=state_with_known), \
         patch("alumni_connector_service.database.save_state"), \
         patch("alumni_connector_service.random_delay"), \
         patch("alumni_connector_service.profile_scraper.scrape_profile") as mock_scrape:

        result = alumni_connector_service.run_alumni_connections(mock_session)

    mock_scrape.assert_not_called()
    assert result["sent"] == 0


# ---------------------------------------------------------------------------
# Test 5: run_alumni_connections resets sent_today on a new day
# ---------------------------------------------------------------------------

def test_run_alumni_connections_resets_on_new_day(monkeypatch, tmp_path):
    """When state.date is yesterday and sent_today=10, the counter resets to 0."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    stale_state = {
        "date": "2026-03-28",  # yesterday relative to today (2026-03-29)
        "sent_today": 10,
        "connected_ids": [],
    }

    mock_session, search_page, profile_page = _make_mock_session()
    # No results so the loop exits cleanly after the reset
    search_page.query_selector_all.return_value = []

    saved_states = []

    def _fake_save(filename, data):
        saved_states.append(data)

    with patch("alumni_connector_service.database.load_state", return_value=stale_state), \
         patch("alumni_connector_service.database.save_state", side_effect=_fake_save), \
         patch("alumni_connector_service.random_delay"):

        result = alumni_connector_service.run_alumni_connections(mock_session)

    # After reset the loop should have run (goto called for at least one firm)
    # and the saved state should reflect sent_today == 0 (no actual sends occurred)
    assert len(saved_states) == 1
    assert saved_states[0]["sent_today"] == 0
    assert result["sent"] == 0
