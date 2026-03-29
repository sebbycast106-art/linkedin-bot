"""
tests/test_connection_tracker_service.py — Unit tests for connection_tracker_service.
"""
import time
import unittest
from unittest.mock import patch, MagicMock, call

import pytest

import connection_tracker_service


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def _empty_state():
    return {
        "pending": [],
        "accepted_count": 0,
        "declined_count": 0,
        "last_check": "",
    }


def _make_mock_session(query_selector_fn=None):
    mock_session = MagicMock()
    mock_page = MagicMock()
    mock_session.new_page.return_value = mock_page
    mock_page.goto = MagicMock()
    mock_page.query_selector.return_value = None
    if query_selector_fn is not None:
        mock_page.query_selector.side_effect = query_selector_fn
    return mock_session, mock_page


# ===========================================================================
# TestAddPendingConnection
# ===========================================================================

class TestAddPendingConnection(unittest.TestCase):

    def test_add_pending_connection(self):
        """add_pending_connection appends a new entry with profile_id, name, and sent_at."""
        initial_state = _empty_state()
        saved_states = []

        with patch(
            "connection_tracker_service.database.load_state",
            return_value=initial_state,
        ), patch(
            "connection_tracker_service.database.save_state",
            side_effect=lambda filename, data: saved_states.append(data),
        ), patch(
            "connection_tracker_service.time.time",
            return_value=1711670400,
        ):
            connection_tracker_service.add_pending_connection("jane-doe-123", "Jane")

        self.assertEqual(len(saved_states), 1)
        saved = saved_states[0]
        self.assertEqual(len(saved["pending"]), 1)
        entry = saved["pending"][0]
        self.assertEqual(entry["profile_id"], "jane-doe-123")
        self.assertEqual(entry["name"], "Jane")
        self.assertEqual(entry["sent_at"], 1711670400)

    def test_caps_at_500(self):
        """When pending already has 500 entries, adding one more keeps it at 500 (oldest removed)."""
        old_entries = [
            {"profile_id": f"old-{i}", "name": f"Person {i}", "sent_at": 1000 + i}
            for i in range(500)
        ]
        initial_state = {
            "pending": old_entries,
            "accepted_count": 0,
            "declined_count": 0,
            "last_check": "",
        }
        saved_states = []

        with patch(
            "connection_tracker_service.database.load_state",
            return_value=initial_state,
        ), patch(
            "connection_tracker_service.database.save_state",
            side_effect=lambda filename, data: saved_states.append(data),
        ), patch(
            "connection_tracker_service.time.time",
            return_value=9999999,
        ):
            connection_tracker_service.add_pending_connection("new-person-501", "New Person")

        self.assertEqual(len(saved_states), 1)
        saved_pending = saved_states[0]["pending"]
        # Still capped at 500
        self.assertEqual(len(saved_pending), 500)
        # The newest entry (just added) must be present
        profile_ids = [e["profile_id"] for e in saved_pending]
        self.assertIn("new-person-501", profile_ids)
        # The very oldest entry (old-0) must have been dropped
        self.assertNotIn("old-0", profile_ids)
        # old-1 through old-499 must still be there (499 entries + 1 new = 500)
        self.assertIn("old-499", profile_ids)


# ===========================================================================
# TestRunAcceptanceCheck
# ===========================================================================

class TestRunAcceptanceCheck(unittest.TestCase):

    def test_skips_recent_entries(self):
        """Entries sent less than 24 hours ago must not trigger a profile visit."""
        state = {
            "pending": [
                {"profile_id": "alice-123", "name": "Alice", "sent_at": int(time.time())},
            ],
            "accepted_count": 0,
            "declined_count": 0,
            "last_check": "",
        }
        mock_session, mock_page = _make_mock_session()

        with patch(
            "connection_tracker_service.database.load_state", return_value=state
        ), patch(
            "connection_tracker_service.database.save_state"
        ), patch(
            "connection_tracker_service.random_delay"
        ), patch(
            "connection_tracker_service.send_telegram"
        ):
            result = connection_tracker_service.run_acceptance_check(mock_session)

        self.assertEqual(result["accepted"], 0)
        # still_pending should include the recent entry
        self.assertEqual(result["still_pending"], 1)
        # No profile page should have been visited
        mock_page.goto.assert_not_called()

    def test_detects_acceptance(self):
        """Entry older than 24h whose profile shows a Message button → accepted."""
        old_sent_at = int(time.time()) - 90000  # 25 hours ago
        state = {
            "pending": [
                {"profile_id": "bob-456", "name": "Bob", "sent_at": old_sent_at},
            ],
            "accepted_count": 0,
            "declined_count": 0,
            "last_check": "",
        }

        mock_msg_btn = MagicMock()

        def _qs(selector):
            if "Message" in selector:
                return mock_msg_btn
            return None

        mock_session, mock_page = _make_mock_session(query_selector_fn=_qs)
        saved_states = []

        with patch(
            "connection_tracker_service.database.load_state", return_value=state
        ), patch(
            "connection_tracker_service.database.save_state",
            side_effect=lambda filename, data: saved_states.append(data),
        ), patch(
            "connection_tracker_service.random_delay"
        ), patch(
            "connection_tracker_service.send_telegram"
        ) as mock_telegram:
            result = connection_tracker_service.run_acceptance_check(mock_session)

        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["still_pending"], 0)

        # accepted_count must be incremented in saved state
        self.assertEqual(saved_states[-1]["accepted_count"], 1)
        # bob-456 must no longer be in pending
        pending_ids = [e["profile_id"] for e in saved_states[-1]["pending"]]
        self.assertNotIn("bob-456", pending_ids)

        # Telegram notification must be sent
        mock_telegram.assert_called_once()
        msg = mock_telegram.call_args[0][0]
        self.assertIn("1", msg)
        self.assertIn("accepted", msg)

        # Profile page must have been visited
        mock_page.goto.assert_called_once_with(
            "https://www.linkedin.com/in/bob-456/", timeout=20000
        )

    def test_detects_declined(self):
        """Entry older than 24h whose profile shows a Connect button → declined/withdrew."""
        old_sent_at = int(time.time()) - 90000
        state = {
            "pending": [
                {"profile_id": "carol-789", "name": "Carol", "sent_at": old_sent_at},
            ],
            "accepted_count": 0,
            "declined_count": 0,
            "last_check": "",
        }

        mock_connect_btn = MagicMock()

        def _qs(selector):
            # Message button not present; Connect button present
            if "Message" in selector:
                return None
            if "Connect" in selector:
                return mock_connect_btn
            return None

        mock_session, mock_page = _make_mock_session(query_selector_fn=_qs)
        saved_states = []

        with patch(
            "connection_tracker_service.database.load_state", return_value=state
        ), patch(
            "connection_tracker_service.database.save_state",
            side_effect=lambda filename, data: saved_states.append(data),
        ), patch(
            "connection_tracker_service.random_delay"
        ), patch(
            "connection_tracker_service.send_telegram"
        ) as mock_telegram:
            result = connection_tracker_service.run_acceptance_check(mock_session)

        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["still_pending"], 0)

        # declined_count must be incremented in saved state
        self.assertEqual(saved_states[-1]["declined_count"], 1)
        # carol-789 must no longer be in pending
        pending_ids = [e["profile_id"] for e in saved_states[-1]["pending"]]
        self.assertNotIn("carol-789", pending_ids)

        # No Telegram notification (only sent for acceptances)
        mock_telegram.assert_not_called()

    def test_max_20_per_run(self):
        """With 25 entries all older than 24h, only 20 profiles are visited; 5 remain pending."""
        old_sent_at = int(time.time()) - 90000
        entries = [
            {"profile_id": f"person-{i}", "name": f"Person {i}", "sent_at": old_sent_at}
            for i in range(25)
        ]
        state = {
            "pending": entries,
            "accepted_count": 0,
            "declined_count": 0,
            "last_check": "",
        }

        # None of the profiles show a Message or Connect button → all remain unknown → still_pending
        mock_session, mock_page = _make_mock_session()
        mock_page.query_selector.return_value = None
        saved_states = []

        with patch(
            "connection_tracker_service.database.load_state", return_value=state
        ), patch(
            "connection_tracker_service.database.save_state",
            side_effect=lambda filename, data: saved_states.append(data),
        ), patch(
            "connection_tracker_service.random_delay"
        ), patch(
            "connection_tracker_service.send_telegram"
        ):
            result = connection_tracker_service.run_acceptance_check(mock_session)

        # 20 profiles visited (goto called 20 times)
        self.assertEqual(mock_page.goto.call_count, 20)
        # 0 accepted (no Message buttons), 25 still pending
        # (20 with unknown state kept + 5 deferred that were never checked)
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["still_pending"], 25)
