"""
tests/test_recruiter_service.py — Unit tests for recruiter_service and related ai_service additions.
"""
import time
import pytest
from unittest.mock import MagicMock, patch

import recruiter_service
import ai_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _make_mock_session():
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page
    mock_page.goto = MagicMock()
    mock_page.query_selector_all.return_value = []
    mock_page.query_selector.return_value = None
    return mock_session, mock_page


# ---------------------------------------------------------------------------
# Test 1: daily limit respected
# ---------------------------------------------------------------------------

def test_daily_limit_respected(tmp_path, monkeypatch):
    """When sent_today == 10 for today, outreach should immediately return {"sent": 0}."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    state = {
        "date": today,
        "sent_today": 10,
        "pending_followup": [],
        "messaged_ids": [],
    }

    with patch("recruiter_service.database.load_state", return_value=state), \
         patch("recruiter_service.database.save_state") as mock_save, \
         patch("recruiter_service.send_telegram"), \
         patch("recruiter_service.apply_limit", return_value=10):

        mock_session = MagicMock()
        result = recruiter_service.run_recruiter_outreach(mock_session)

    assert result == {"sent": 0}
    # new_page should NOT have been called — no browser work
    mock_session.new_page.assert_not_called()
    # state should not have been re-saved (nothing changed)
    mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: date reset
# ---------------------------------------------------------------------------

def test_date_reset(monkeypatch):
    """When state has yesterday's date, sent_today resets to 0 before the run."""
    state = {
        "date": "2020-01-01",  # clearly in the past
        "sent_today": 7,
        "pending_followup": [],
        "messaged_ids": [],
    }

    mock_session, mock_page = _make_mock_session()

    with patch("recruiter_service.database.load_state", return_value=state), \
         patch("recruiter_service.database.save_state") as mock_save, \
         patch("recruiter_service.random_delay"), \
         patch("recruiter_service.send_telegram"):

        result = recruiter_service.run_recruiter_outreach(mock_session)

    # No results → sent == 0, but the function completed without hitting old limit
    assert result == {"sent": 0}
    # save_state should have been called; verify the saved state has sent_today == 0
    assert mock_save.called
    saved_state = mock_save.call_args[0][1]
    assert saved_state["sent_today"] == 0


# ---------------------------------------------------------------------------
# Test 3: followup skips recent entries
# ---------------------------------------------------------------------------

def test_followup_skips_recent(monkeypatch):
    """Entries added just now (< 24 hrs) should not trigger a profile visit."""
    state = {
        "date": "2026-03-28",
        "sent_today": 2,
        "pending_followup": [
            {
                "profile_id": "alice-123",
                "name": "Alice",
                "company": "Fidelity",
                "sent_at": time.time(),  # just now
            }
        ],
        "messaged_ids": [],
    }

    mock_session, mock_page = _make_mock_session()

    with patch("recruiter_service.database.load_state", return_value=state), \
         patch("recruiter_service.database.save_state"), \
         patch("recruiter_service.random_delay"), \
         patch("recruiter_service.send_telegram"):

        result = recruiter_service.run_followup_check(mock_session)

    assert result == {"messaged": 0}
    mock_page.goto.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: followup visits old entries and messages when button present
# ---------------------------------------------------------------------------

def test_followup_visits_old_entries(monkeypatch):
    """Entry older than 24 hrs with Message button → follow-up sent, messaged count == 1."""
    state = {
        "date": "2026-03-28",
        "sent_today": 1,
        "pending_followup": [
            {
                "profile_id": "bob-456",
                "name": "Bob",
                "company": "BlackRock",
                "sent_at": time.time() - 90000,  # 25 hrs ago
            }
        ],
        "messaged_ids": [],
    }

    mock_session, mock_page = _make_mock_session()
    # Simulate Message button present
    mock_msg_btn = MagicMock()
    mock_msg_box = MagicMock()
    mock_send_btn = MagicMock()

    def _query_selector(selector):
        if "Message" in selector:
            return mock_msg_btn
        if "msg-form__contenteditable" in selector:
            return mock_msg_box
        if "msg-form__send-button" in selector:
            return mock_send_btn
        return None

    mock_page.query_selector.side_effect = _query_selector

    with patch("recruiter_service.database.load_state", return_value=state), \
         patch("recruiter_service.database.save_state"), \
         patch("recruiter_service.random_delay"), \
         patch("recruiter_service.send_telegram"), \
         patch(
             "recruiter_service.ai_service.generate_recruiter_followup_message",
             return_value="Hi Bob, I'm a Northeastern sophomore...",
         ):

        result = recruiter_service.run_followup_check(mock_session)

    assert result == {"messaged": 1}
    mock_page.goto.assert_called_once_with(
        "https://www.linkedin.com/in/bob-456/", timeout=20000
    )


# ---------------------------------------------------------------------------
# Test 5: state persists pending_followup entries after outreach
# ---------------------------------------------------------------------------

def test_recruiter_state_persists(tmp_path, monkeypatch):
    """After outreach with a mocked Connect-button hit, pending_followup is saved."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

    mock_session, mock_page = _make_mock_session()

    # Build a fake result element that yields a profile with a Connect button
    mock_result = MagicMock()

    mock_name_el = MagicMock()
    mock_name_el.inner_text.return_value = "Jane Doe"

    mock_title_el = MagicMock()
    mock_title_el.inner_text.return_value = "Campus Recruiter at Fidelity"

    mock_link_el = MagicMock()
    mock_link_el.get_attribute.return_value = "https://www.linkedin.com/in/jane-doe-789/"

    mock_connect_btn = MagicMock()
    mock_send_btn = MagicMock()

    def _result_qs(selector):
        if "title-text" in selector:
            return mock_name_el
        if "primary-subtitle" in selector:
            return mock_title_el
        if "/in/" in selector:
            return mock_link_el
        if "Connect" in selector:
            return mock_connect_btn
        return None

    mock_result.query_selector.side_effect = _result_qs

    # First call returns our fake result; subsequent calls (close button etc.) return []
    mock_page.query_selector_all.return_value = [mock_result]

    def _page_qs(selector):
        if "Send now" in selector or "Send invitation" in selector:
            return mock_send_btn
        return None

    mock_page.query_selector.side_effect = _page_qs

    saved_states = []

    def _save(filename, data):
        saved_states.append(data)

    with patch("recruiter_service.random_delay"), \
         patch("recruiter_service.send_telegram"), \
         patch(
             "recruiter_service.ai_service.generate_connection_message",
             return_value="Hi Jane!",
         ), \
         patch("recruiter_service.database.save_state", side_effect=_save), \
         patch(
             "recruiter_service.database.load_state",
             return_value={
                 "date": today,
                 "sent_today": 0,
                 "pending_followup": [],
                 "messaged_ids": [],
             },
         ):

        result = recruiter_service.run_recruiter_outreach(mock_session)

    assert result["sent"] == 1
    # At least one save should have pending_followup with jane-doe-789
    all_profiles = [
        entry["profile_id"]
        for s in saved_states
        for entry in s.get("pending_followup", [])
    ]
    assert "jane-doe-789" in all_profiles


# ---------------------------------------------------------------------------
# Test 6: generate_recruiter_followup_message returns a string
# ---------------------------------------------------------------------------

def test_generate_recruiter_followup_message():
    """Mock Anthropic client; verify function returns a non-empty string."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(text="Hi Sarah, I'm a Northeastern sophomore exploring fintech co-ops...")
    ]
    mock_client.messages.create.return_value = mock_response

    with patch("ai_service.anthropic.Anthropic", return_value=mock_client):
        result = ai_service.generate_recruiter_followup_message("Sarah", "Fidelity")

    assert isinstance(result, str)
    assert len(result) > 5
    assert len(result) <= 299
