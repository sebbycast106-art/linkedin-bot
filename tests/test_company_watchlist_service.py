"""
tests/test_company_watchlist_service.py — Unit tests for company_watchlist_service.
"""
import pytest
from unittest.mock import MagicMock, patch

import company_watchlist_service
from company_watchlist_service import _WATCHLIST


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _make_card(job_id, title="Software Intern", location="New York, NY"):
    """Build a mock job card element."""
    card = MagicMock()

    title_el = MagicMock()
    title_el.inner_text.return_value = title

    link_el = MagicMock()
    link_el.get_attribute.return_value = f"https://www.linkedin.com/jobs/view/{job_id}/"

    location_el = MagicMock()
    location_el.inner_text.return_value = location

    def _qs(sel):
        if "base-search-card__title" in sel or "job-search-card__title" in sel:
            return title_el
        if "base-card__full-link" in sel:
            return link_el
        if "job-search-card__location" in sel:
            return location_el
        return None

    card.query_selector.side_effect = _qs
    return card


def _make_session(cards=None):
    """Build a mock session returning the given cards for all companies."""
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page
    mock_page.query_selector_all.return_value = cards if cards is not None else []
    mock_page.query_selector.return_value = None
    mock_page.wait_for_selector = MagicMock()
    return mock_session, mock_page


# ---------------------------------------------------------------------------
# Test 1: skip already-seen job IDs
# ---------------------------------------------------------------------------

def test_skips_seen_job_ids():
    """A job ID already in state should not trigger an alert."""
    mock_session, mock_page = _make_session(cards=[_make_card("j1")])

    with patch("company_watchlist_service.database.load_state",
               return_value={"seen_ids": ["j1"]}), \
         patch("company_watchlist_service.database.save_state"), \
         patch("company_watchlist_service.random_delay"), \
         patch("company_watchlist_service.send_telegram") as mock_tg:

        result = company_watchlist_service.run_watchlist_check(mock_session)

    assert result["alerts_sent"] == 0
    mock_tg.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: alert on new job
# ---------------------------------------------------------------------------

def test_alerts_on_new_job():
    """A new (unseen) job ID should trigger a Telegram alert containing '🚨'."""
    mock_session, mock_page = _make_session(cards=[_make_card("new_job_1")])

    with patch("company_watchlist_service.database.load_state",
               return_value={"seen_ids": []}), \
         patch("company_watchlist_service.database.save_state"), \
         patch("company_watchlist_service.random_delay"), \
         patch("company_watchlist_service.send_telegram") as mock_tg:

        result = company_watchlist_service.run_watchlist_check(mock_session)

    # One alert per company that finds this card (all companies share same mock page)
    assert result["alerts_sent"] >= 1
    mock_tg.assert_called()
    first_call_msg = mock_tg.call_args_list[0][0][0]
    assert "🚨" in first_call_msg


# ---------------------------------------------------------------------------
# Test 3: new job saved to state
# ---------------------------------------------------------------------------

def test_new_job_saved_to_state():
    """After a new job is found, its ID should be persisted in watchlist_state."""
    mock_session, mock_page = _make_session(cards=[_make_card("save_me_123")])

    saved_states = []

    def _save(filename, data):
        saved_states.append((filename, data))

    with patch("company_watchlist_service.database.load_state",
               return_value={"seen_ids": []}), \
         patch("company_watchlist_service.database.save_state", side_effect=_save), \
         patch("company_watchlist_service.random_delay"), \
         patch("company_watchlist_service.send_telegram"):

        company_watchlist_service.run_watchlist_check(mock_session)

    assert len(saved_states) == 1
    _, saved_data = saved_states[0]
    assert "save_me_123" in saved_data["seen_ids"]


# ---------------------------------------------------------------------------
# Test 4: all companies checked
# ---------------------------------------------------------------------------

def test_checks_all_companies():
    """companies_checked should equal the total number of entries in _WATCHLIST."""
    mock_session, mock_page = _make_session(cards=[])

    with patch("company_watchlist_service.database.load_state",
               return_value={"seen_ids": []}), \
         patch("company_watchlist_service.database.save_state"), \
         patch("company_watchlist_service.random_delay"), \
         patch("company_watchlist_service.send_telegram"):

        result = company_watchlist_service.run_watchlist_check(mock_session)

    assert result["companies_checked"] == len(_WATCHLIST)


# ---------------------------------------------------------------------------
# Test 5: company error continues to next
# ---------------------------------------------------------------------------

def test_company_error_continues():
    """An exception on the first company should not stop remaining companies from being checked."""
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page
    mock_page.query_selector_all.return_value = []
    mock_page.query_selector.return_value = None
    mock_page.wait_for_selector = MagicMock()

    call_count = 0

    def _goto(url, timeout=20000):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("network error on first company")

    mock_page.goto.side_effect = _goto

    with patch("company_watchlist_service.database.load_state",
               return_value={"seen_ids": []}), \
         patch("company_watchlist_service.database.save_state"), \
         patch("company_watchlist_service.random_delay"), \
         patch("company_watchlist_service.send_telegram"):

        result = company_watchlist_service.run_watchlist_check(mock_session)

    # First company errored (not counted), remaining should be checked
    assert result["companies_checked"] == len(_WATCHLIST) - 1
