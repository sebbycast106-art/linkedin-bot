"""
tests/test_connector_service.py — Unit tests for connector_service enrichment flow.
"""
import pytest
from unittest.mock import MagicMock, patch

import connector_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _make_mock_session_with_profile():
    """Return (mock_session, search_page, profile_page) with two distinct pages."""
    mock_session = MagicMock()
    search_page = MagicMock()
    profile_page = MagicMock()

    # session.new_page() returns search_page first, then profile_page
    mock_session.new_page.side_effect = [search_page, profile_page]

    # Default: no results
    search_page.goto = MagicMock()
    search_page.query_selector_all.return_value = []
    search_page.query_selector.return_value = None

    return mock_session, search_page, profile_page


def _make_result_element(name="Alex Smith", title="Finance Intern at Fidelity", href="https://www.linkedin.com/in/alex-smith-123/"):
    """Build a mock search-result DOM element."""
    mock_result = MagicMock()

    mock_name_el = MagicMock()
    mock_name_el.inner_text.return_value = name

    mock_title_el = MagicMock()
    mock_title_el.inner_text.return_value = title

    mock_link_el = MagicMock()
    mock_link_el.get_attribute.return_value = href

    mock_connect_btn = MagicMock()

    def _result_qs(selector):
        if "title-text" in selector:
            return mock_name_el
        if "primary-subtitle" in selector:
            return mock_title_el
        if "/in/" in selector:
            return mock_link_el
        if "Connect" in selector or "Invite" in selector:
            return mock_connect_btn
        return None

    mock_result.query_selector.side_effect = _result_qs
    return mock_result, mock_connect_btn


# ---------------------------------------------------------------------------
# Test 1: profile_scraper.scrape_profile is called during connection flow
# ---------------------------------------------------------------------------

def test_profile_enrichment_called(tmp_path, monkeypatch):
    """profile_scraper.scrape_profile should be called with the profile URL."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    mock_session, search_page, profile_page = _make_mock_session_with_profile()
    mock_result, mock_connect_btn = _make_result_element()

    mock_send_btn = MagicMock()

    def _page_qs(selector):
        if "Send now" in selector or "Send invitation" in selector:
            return mock_send_btn
        return None

    search_page.query_selector_all.return_value = [mock_result]
    search_page.query_selector.side_effect = _page_qs

    enrichment_data = {"school": "Northeastern", "headline": "Finance Intern"}

    with patch("connector_service.profile_scraper.scrape_profile", return_value=enrichment_data) as mock_scrape, \
         patch("connector_service.ai_service.generate_connection_message", return_value="hi") as mock_gen, \
         patch("connector_service.random_delay"), \
         patch("connector_service.database.load_state", return_value={
             "date": today,
             "connects_today": 0,
             "connected_ids": [],
         }), \
         patch("connector_service.database.save_state"):

        result = connector_service.run_daily_connections(mock_session)

    mock_scrape.assert_called_once_with(profile_page, "https://www.linkedin.com/in/alex-smith-123/")
    assert result >= 0  # connector ran without error


# ---------------------------------------------------------------------------
# Test 2: enrichment failure (empty dict) does not crash the connector
# ---------------------------------------------------------------------------

def test_enrichment_failure_doesnt_crash(tmp_path, monkeypatch):
    """When profile_scraper returns {}, connector should still proceed normally."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    mock_session, search_page, profile_page = _make_mock_session_with_profile()
    mock_result, mock_connect_btn = _make_result_element()

    mock_send_btn = MagicMock()

    def _page_qs(selector):
        if "Send now" in selector or "Send invitation" in selector:
            return mock_send_btn
        return None

    search_page.query_selector_all.return_value = [mock_result]
    search_page.query_selector.side_effect = _page_qs

    with patch("connector_service.profile_scraper.scrape_profile", return_value={}) as mock_scrape, \
         patch("connector_service.ai_service.generate_connection_message", return_value="hi"), \
         patch("connector_service.random_delay"), \
         patch("connector_service.database.load_state", return_value={
             "date": today,
             "connects_today": 0,
             "connected_ids": [],
         }), \
         patch("connector_service.database.save_state"):

        # Should not raise
        result = connector_service.run_daily_connections(mock_session)

    mock_scrape.assert_called_once()
    assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Test 3: enrichment kwargs passed to generate_connection_message
# ---------------------------------------------------------------------------

def test_enrichment_kwargs_forwarded(tmp_path, monkeypatch):
    """school and headline from enrichment are forwarded to ai_service."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    mock_session, search_page, profile_page = _make_mock_session_with_profile()
    mock_result, mock_connect_btn = _make_result_element()

    mock_add_note_btn = MagicMock()
    mock_send_btn = MagicMock()
    mock_note_box = MagicMock()

    call_sequence = []

    def _page_qs(selector):
        if "Add a note" in selector:
            return mock_add_note_btn
        if "Send now" in selector or "Send invitation" in selector:
            return mock_send_btn
        if "custom-message" in selector:
            return mock_note_box
        return None

    search_page.query_selector_all.return_value = [mock_result]
    search_page.query_selector.side_effect = _page_qs

    enrichment_data = {"school": "Northeastern University", "headline": "Finance Intern at Goldman"}

    with patch("connector_service.profile_scraper.scrape_profile", return_value=enrichment_data), \
         patch("connector_service.ai_service.generate_connection_message", return_value="Hello!") as mock_gen, \
         patch("connector_service.random_delay"), \
         patch("connector_service.database.load_state", return_value={
             "date": today,
             "connects_today": 0,
             "connected_ids": [],
         }), \
         patch("connector_service.database.save_state"):

        connector_service.run_daily_connections(mock_session)

    mock_gen.assert_called_once()
    _, kwargs = mock_gen.call_args
    assert kwargs.get("school") == "Northeastern University"
    assert kwargs.get("headline") == "Finance Intern at Goldman"
