"""
inbox_monitor_service.py — Monitor LinkedIn inbox for recruiter messages and draft replies.

Sends Telegram alerts with draft replies for recruiter-initiated messages.
State file: inbox_state.json — tracks seen thread IDs to avoid duplicate alerts.

Public interface:
    run_inbox_check(session) -> dict  # {"found": N, "notified": N}
"""
import database
import ai_service
from linkedin_session import random_delay
from telegram_service import send_telegram

_STATE_FILE = "inbox_state.json"
_DEFAULT_STATE = {"seen_thread_ids": []}

_RECRUITER_KEYWORDS = [
    "opportunity", "role", "position", "opening", "reach out",
    "co-op", "intern", "internship", "your background", "your profile",
    "interested in you", "recruiting", "hiring", "candidate",
]


def run_inbox_check(session) -> dict:
    """Check LinkedIn inbox for new recruiter messages and send Telegram alerts.

    Returns {"found": N, "notified": N}.
    """
    state = database.load_state(_STATE_FILE, _DEFAULT_STATE)
    seen_thread_ids = state.get("seen_thread_ids", [])

    found = 0
    notified = 0

    page = session.new_page()
    try:
        page.goto("https://www.linkedin.com/messaging/", timeout=20000)
        random_delay(3, 4)

        threads = page.query_selector_all(
            ".msg-conversation-listitem, .msg-conversations-container__convo-item"
        )

        for thread in threads[:10]:
            # Extract thread_id from href
            thread_id = None
            link_el = thread.query_selector("a[href*='/messaging/thread/']")
            if link_el:
                href = link_el.get_attribute("href") or ""
                # href like /messaging/thread/2-abc123/
                parts = [p for p in href.split("/") if p]
                if "thread" in parts:
                    idx = parts.index("thread")
                    if idx + 1 < len(parts):
                        thread_id = parts[idx + 1]

            if not thread_id:
                continue

            if thread_id in seen_thread_ids:
                continue

            # Only process unread threads
            unread_el = thread.query_selector(
                ".msg-conversation-listitem__unread-count, .notification-badge"
            )
            if not unread_el:
                seen_thread_ids.append(thread_id)
                continue

            # Click to open the thread
            thread.click()
            random_delay(1, 2)

            # Get sender name
            sender_name = ""
            name_el = page.query_selector(
                ".msg-s-message-group__name, .msg-entity-lockup__entity-title"
            )
            if name_el:
                sender_name = name_el.inner_text().strip()

            # Get sender title
            sender_title = ""
            title_el = page.query_selector(".msg-entity-lockup__subtitle")
            if title_el:
                sender_title = title_el.inner_text().strip()

            # Get latest message text
            message_text = ""
            message_els = page.query_selector_all(
                ".msg-s-event-listitem__body .msg-s-event__content, "
                ".msg-s-message-list__event .msg-s-event-listitem__body"
            )
            if message_els:
                last_el = message_els[-1]
                message_text = last_el.inner_text().strip()

            found += 1

            # Check if recruiter-initiated
            is_recruiter = any(kw in message_text.lower() for kw in _RECRUITER_KEYWORDS)

            if is_recruiter:
                draft = ai_service.generate_inbox_reply(sender_name, sender_title, message_text)
                alert = (
                    f"📩 LinkedIn message from {sender_name} ({sender_title}):\n\n"
                    f'"{message_text[:200]}"\n\n'
                    f'💬 Draft reply:\n"{draft}"'
                )
                send_telegram(alert)
                notified += 1

            seen_thread_ids.append(thread_id)
            random_delay(2, 3)

    finally:
        page.close()

    # Keep only last 500 seen thread IDs
    state["seen_thread_ids"] = seen_thread_ids[-500:]
    database.save_state(_STATE_FILE, state)

    print(f"[inbox_monitor] checked {found} threads, notified {notified}", flush=True)
    return {"found": found, "notified": notified}
