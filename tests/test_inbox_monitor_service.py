"""
tests/test_inbox_monitor_service.py — Unit tests for inbox_monitor_service and generate_inbox_reply.
"""
import pytest
from unittest.mock import MagicMock, patch

import inbox_monitor_service
import ai_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _make_thread(thread_id, unread=True, message_text="Hey how are you",
                 sender_name="Alice", sender_title="Recruiter at Acme"):
    """Build a mock thread element."""
    thread = MagicMock()

    # Link element for thread_id extraction
    link_el = MagicMock()
    link_el.get_attribute.return_value = f"/messaging/thread/{thread_id}/"
    thread.query_selector.side_effect = lambda sel: (
        link_el if "/messaging/thread/" in sel else
        (MagicMock() if unread and (
            "unread-count" in sel or "notification-badge" in sel
        ) else None)
    )

    return thread, sender_name, sender_title, message_text


def _make_mock_session(threads, sender_name="Alice", sender_title="Recruiter at Acme",
                       message_text="Hey how are you"):
    """Build a mock session whose page returns the given thread mocks."""
    session = MagicMock()
    page = MagicMock()
    session.new_page.return_value = page
    page.goto = MagicMock()
    page.query_selector_all.side_effect = lambda sel: (
        threads if "msg-conversation-listitem" in sel else _make_message_els(message_text)
    )

    name_el = MagicMock()
    name_el.inner_text.return_value = sender_name
    title_el = MagicMock()
    title_el.inner_text.return_value = sender_title

    def _qs(sel):
        if "msg-s-message-group__name" in sel or "entity-title" in sel:
            return name_el
        if "subtitle" in sel:
            return title_el
        return None

    page.query_selector.side_effect = _qs
    return session, page


def _make_message_els(text):
    el = MagicMock()
    el.inner_text.return_value = text
    return [el]


# ---------------------------------------------------------------------------
# Test 1: skip already-seen threads
# ---------------------------------------------------------------------------

def test_skips_seen_threads():
    """Thread with id already in seen_thread_ids should not trigger any alert."""
    thread, sender_name, sender_title, msg_text = _make_thread("t1", message_text="great opportunity")
    session, page = _make_mock_session([thread])

    initial_state = {"seen_thread_ids": ["t1"]}

    with patch("inbox_monitor_service.database.load_state", return_value=initial_state), \
         patch("inbox_monitor_service.database.save_state"), \
         patch("inbox_monitor_service.random_delay"), \
         patch("inbox_monitor_service.send_telegram") as mock_tg:

        result = inbox_monitor_service.run_inbox_check(session)

    assert result["notified"] == 0
    mock_tg.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2: non-recruiter message not notified
# ---------------------------------------------------------------------------

def test_non_recruiter_message_not_notified():
    """Message with no recruiter keywords should not send a Telegram alert."""
    thread, sender_name, sender_title, msg_text = _make_thread(
        "t2", message_text="Hey how are you"
    )
    session, page = _make_mock_session([thread], message_text="Hey how are you")

    with patch("inbox_monitor_service.database.load_state",
               return_value={"seen_thread_ids": []}), \
         patch("inbox_monitor_service.database.save_state"), \
         patch("inbox_monitor_service.random_delay"), \
         patch("inbox_monitor_service.send_telegram") as mock_tg:

        result = inbox_monitor_service.run_inbox_check(session)

    assert result["notified"] == 0
    mock_tg.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: recruiter message triggers Telegram
# ---------------------------------------------------------------------------

def test_recruiter_message_triggers_telegram():
    """Message containing a recruiter keyword should send Telegram alerts including '📩'."""
    thread, sender_name, sender_title, msg_text = _make_thread(
        "t3", message_text="We have a great opportunity for you"
    )
    session, page = _make_mock_session(
        [thread],
        sender_name="Bob Smith",
        sender_title="Campus Recruiter at Goldman",
        message_text="We have a great opportunity for you",
    )

    with patch("inbox_monitor_service.database.load_state",
               return_value={"seen_thread_ids": []}), \
         patch("inbox_monitor_service.database.save_state"), \
         patch("inbox_monitor_service.random_delay"), \
         patch("inbox_monitor_service.send_telegram") as mock_tg, \
         patch("inbox_monitor_service.ai_service.generate_inbox_reply",
               return_value="draft reply"), \
         patch("inbox_monitor_service.generate_reply_draft",
               return_value="Here's my draft reply."):

        result = inbox_monitor_service.run_inbox_check(session)

    assert result["notified"] == 1
    # Now sends two messages: the alert and the draft approval prompt
    assert mock_tg.call_count == 2
    first_alert = mock_tg.call_args_list[0][0][0]
    assert "📩" in first_alert
    second_msg = mock_tg.call_args_list[1][0][0]
    assert "SEND_t3" in second_msg
    assert "SKIP_t3" in second_msg


# ---------------------------------------------------------------------------
# Test 4: thread marked seen after processing
# ---------------------------------------------------------------------------

def test_thread_marked_seen_after_processing():
    """After processing, thread_id should be added to seen_thread_ids in saved state."""
    thread, sender_name, sender_title, msg_text = _make_thread(
        "t4", message_text="Hey how are you"
    )
    session, page = _make_mock_session([thread], message_text="Hey how are you")

    saved_states = []

    def _save(filename, data):
        saved_states.append(data)

    with patch("inbox_monitor_service.database.load_state",
               return_value={"seen_thread_ids": []}), \
         patch("inbox_monitor_service.database.save_state", side_effect=_save), \
         patch("inbox_monitor_service.random_delay"), \
         patch("inbox_monitor_service.send_telegram"):

        inbox_monitor_service.run_inbox_check(session)

    assert len(saved_states) == 1
    assert "t4" in saved_states[0]["seen_thread_ids"]


# ---------------------------------------------------------------------------
# Test 5: empty inbox returns zero
# ---------------------------------------------------------------------------

def test_empty_inbox_returns_zero():
    """When there are no thread elements, return {"found": 0, "notified": 0}."""
    session, page = _make_mock_session([])
    page.query_selector_all.return_value = []

    with patch("inbox_monitor_service.database.load_state",
               return_value={"seen_thread_ids": []}), \
         patch("inbox_monitor_service.database.save_state"), \
         patch("inbox_monitor_service.random_delay"), \
         patch("inbox_monitor_service.send_telegram"):

        result = inbox_monitor_service.run_inbox_check(session)

    assert result == {"found": 0, "notified": 0}


# ---------------------------------------------------------------------------
# Test 6: generate_inbox_reply returns string
# ---------------------------------------------------------------------------

def test_generate_inbox_reply_returns_string():
    """Mock Anthropic; verify generate_inbox_reply returns a non-empty string."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Thanks for reaching out! I'm very interested in fintech co-ops.")]
    mock_client.messages.create.return_value = mock_response

    with patch("ai_service.anthropic.Anthropic", return_value=mock_client):
        result = ai_service.generate_inbox_reply(
            sender_name="Jane Recruiter",
            sender_title="Talent Acquisition at Fidelity",
            message_text="We have an exciting opportunity that matches your background.",
        )

    assert isinstance(result, str)
    assert len(result) > 5


# ---------------------------------------------------------------------------
# Test 7: generate_inbox_reply returns None on error
# ---------------------------------------------------------------------------

def test_generate_inbox_reply_returns_none_on_error():
    """When Anthropic raises an exception, generate_inbox_reply should return None."""
    with patch("ai_service.anthropic.Anthropic", side_effect=Exception("API error")):
        result = ai_service.generate_inbox_reply(
            sender_name="Jane",
            sender_title="Recruiter",
            message_text="We have a great opportunity.",
        )

    assert result is None
