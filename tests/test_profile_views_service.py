"""
tests/test_profile_views_service.py — Unit tests for profile_views_service.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import profile_views_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _yesterday() -> str:
    today = datetime.now(ZoneInfo("America/New_York")).date()
    return (today - timedelta(days=1)).isoformat()


def _make_mock_session(viewer_cards=None):
    """Return a mock session whose new_page returns a page with the given viewer cards."""
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page
    mock_page.query_selector_all.return_value = viewer_cards if viewer_cards is not None else []
    mock_page.query_selector.return_value = None
    return mock_session, mock_page


def _make_viewer_card(profile_id="john-doe-123", name="John Doe", title="Engineer at Acme"):
    """Build a mock viewer card DOM element."""
    card = MagicMock()

    link_el = MagicMock()
    link_el.get_attribute.return_value = f"https://www.linkedin.com/in/{profile_id}/"

    name_el = MagicMock()
    name_el.inner_text.return_value = name

    title_el = MagicMock()
    title_el.inner_text.return_value = title

    connect_btn = MagicMock()

    def _card_qs(selector):
        if "/in/" in selector:
            return link_el
        if "aria-hidden" in selector or selector == "h3":
            return name_el
        if "subtitle" in selector or "primary-subtitle" in selector:
            return title_el
        if "Connect" in selector:
            return connect_btn
        return None

    card.query_selector.side_effect = _card_qs
    return card, connect_btn


# ---------------------------------------------------------------------------
# Test 1: daily limit respected
# ---------------------------------------------------------------------------

def test_daily_limit_respected():
    """When sent_today=10 for today, function returns immediately with sent=0, checked=0."""
    mock_session, mock_page = _make_mock_session()

    state = {"date": _today(), "sent_today": 10, "connected_viewer_ids": []}

    with patch("profile_views_service.database.load_state", return_value=state), \
         patch("profile_views_service.database.save_state"), \
         patch("profile_views_service.random_delay"):

        result = profile_views_service.run_profile_views_connect(mock_session)

    assert result == {"sent": 0, "checked": 0}
    # session.new_page should never have been called since we bail out early
    mock_session.new_page.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: date reset clears count
# ---------------------------------------------------------------------------

def test_date_reset_clears_count():
    """When state has yesterday's date with sent_today=10, the limit is reset and function runs."""
    mock_session, mock_page = _make_mock_session(viewer_cards=[])

    stale_state = {"date": _yesterday(), "sent_today": 10, "connected_viewer_ids": []}

    with patch("profile_views_service.database.load_state", return_value=stale_state), \
         patch("profile_views_service.database.save_state"), \
         patch("profile_views_service.random_delay"):

        result = profile_views_service.run_profile_views_connect(mock_session)

    # Function ran (did not bail out early), returned normally with no viewers
    assert result == {"sent": 0, "checked": 0}
    mock_session.new_page.assert_called()


# ---------------------------------------------------------------------------
# Test 3: skips already connected viewer
# ---------------------------------------------------------------------------

def test_skips_already_connected():
    """Viewer whose profile_id is already in connected_viewer_ids should not be connected."""
    profile_id = "john-doe"
    card, connect_btn = _make_viewer_card(profile_id=profile_id)

    mock_session, mock_page = _make_mock_session(viewer_cards=[card])

    state = {
        "date": _today(),
        "sent_today": 0,
        "connected_viewer_ids": [profile_id],
    }

    with patch("profile_views_service.database.load_state", return_value=state), \
         patch("profile_views_service.database.save_state"), \
         patch("profile_views_service.random_delay"), \
         patch("profile_views_service.profile_scraper.scrape_profile", return_value={}), \
         patch("profile_views_service.ai_service.generate_connection_message", return_value="hi"):

        result = profile_views_service.run_profile_views_connect(mock_session)

    assert result["sent"] == 0
    connect_btn.click.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: connects new viewer
# ---------------------------------------------------------------------------

def test_connects_new_viewer():
    """A new viewer with a Connect button should result in sent=1 and profile_id in state."""
    profile_id = "jane-smith-456"
    card, connect_btn = _make_viewer_card(profile_id=profile_id, name="Jane Smith", title="Analyst at Fidelity")

    # Main page: no "Add a note" button, but has a "Send now" button
    mock_session = MagicMock()
    main_page = MagicMock()
    profile_page = MagicMock()

    # first new_page() -> main analytics page, subsequent -> profile scraping pages
    main_page.query_selector_all.return_value = [card]

    send_btn = MagicMock()

    def _main_page_qs(selector):
        if "Send now" in selector or "Send invitation" in selector:
            return send_btn
        return None

    main_page.query_selector.side_effect = _main_page_qs

    call_count = {"n": 0}

    def _new_page():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return main_page
        return profile_page

    mock_session.new_page.side_effect = _new_page

    state = {"date": _today(), "sent_today": 0, "connected_viewer_ids": []}
    saved_state = {}

    def _save_state(filename, data):
        saved_state.update(data)

    with patch("profile_views_service.database.load_state", return_value=state), \
         patch("profile_views_service.database.save_state", side_effect=_save_state), \
         patch("profile_views_service.random_delay"), \
         patch("profile_views_service.profile_scraper.scrape_profile", return_value={"school": "Northeastern"}) as mock_scrape, \
         patch("profile_views_service.ai_service.generate_connection_message", return_value="hi"):

        result = profile_views_service.run_profile_views_connect(mock_session)

    assert result["sent"] == 1
    assert profile_id in saved_state.get("connected_viewer_ids", [])
    mock_scrape.assert_called_once_with(
        profile_page, f"https://www.linkedin.com/in/{profile_id}/"
    )


# ---------------------------------------------------------------------------
# Test 5: no viewers returns zero
# ---------------------------------------------------------------------------

def test_no_viewers_returns_zero():
    """Empty viewer list should return {"sent": 0, "checked": 0}."""
    mock_session, mock_page = _make_mock_session(viewer_cards=[])

    state = {"date": _today(), "sent_today": 0, "connected_viewer_ids": []}

    with patch("profile_views_service.database.load_state", return_value=state), \
         patch("profile_views_service.database.save_state"), \
         patch("profile_views_service.random_delay"):

        result = profile_views_service.run_profile_views_connect(mock_session)

    assert result == {"sent": 0, "checked": 0}
