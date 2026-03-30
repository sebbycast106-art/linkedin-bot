"""
message_scheduler_service.py — Queue message reminders for optimal send times.

Does NOT send LinkedIn messages. It queues reminders and sends them to Telegram
when the optimal send window arrives.

Public interface:
    queue_message(profile_id, name, message_draft, reason, send_after=None) -> str
    run_message_queue() -> dict  # {"reminded": N, "expired": N}
    get_queue() -> list[dict]
"""
import uuid
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import database
from telegram_service import send_telegram

_STATE_FILE = "message_queue_state.json"
_DEFAULT_STATE = {"queue": []}

_ET = ZoneInfo("America/New_York")

# Optimal send windows: Tue(1), Wed(2), Thu(3) — weekday numbers (Mon=0)
_OPTIMAL_DAYS = {1, 2, 3}  # Tue, Wed, Thu
_OPTIMAL_HOURS = [(9, 11), (13, 15)]  # 9-11 AM ET, 1-3 PM ET

_EXPIRE_DAYS = 7


def _in_optimal_window(dt: datetime) -> bool:
    """Check if a datetime (in ET) falls within an optimal send window."""
    if dt.weekday() not in _OPTIMAL_DAYS:
        return False
    hour = dt.hour
    return any(start <= hour < end for start, end in _OPTIMAL_HOURS)


def _next_optimal_window(now_et: datetime) -> datetime:
    """Calculate the next optimal send window from the given ET datetime."""
    # Try today first if we haven't passed all windows
    candidate = now_et.replace(minute=0, second=0, microsecond=0)

    for day_offset in range(8):  # at most 7 days ahead
        check_day = candidate + timedelta(days=day_offset)
        if check_day.weekday() not in _OPTIMAL_DAYS:
            continue
        for start_hour, _end_hour in _OPTIMAL_HOURS:
            window_start = check_day.replace(hour=start_hour, minute=0, second=0, microsecond=0)
            if window_start > now_et:
                return window_start
            # If we're currently in this window (same day_offset=0)
            if day_offset == 0 and _in_optimal_window(now_et):
                return now_et

    # Fallback: next Tuesday at 9 AM ET
    days_until_tue = (1 - now_et.weekday()) % 7
    if days_until_tue == 0:
        days_until_tue = 7
    return (now_et + timedelta(days=days_until_tue)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )


def queue_message(
    profile_id: str,
    name: str,
    message_draft: str,
    reason: str,
    send_after: datetime | None = None,
) -> str:
    """Add a message reminder to the queue.

    If send_after is None, calculates the next optimal send window.
    Returns confirmation string.
    """
    state = database.load_state(_STATE_FILE, default=dict(_DEFAULT_STATE))
    queue = state.get("queue", [])

    now_et = datetime.now(_ET)

    if send_after is None:
        if _in_optimal_window(now_et):
            send_after = now_et
        else:
            send_after = _next_optimal_window(now_et)

    # Ensure send_after is timezone-aware
    if send_after.tzinfo is None:
        send_after = send_after.replace(tzinfo=_ET)

    entry = {
        "id": uuid.uuid4().hex[:8],
        "profile_id": profile_id,
        "name": name,
        "message_draft": message_draft,
        "reason": reason,
        "status": "pending",  # pending | reminded | expired
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "send_after": send_after.isoformat(),
    }

    queue.append(entry)
    state["queue"] = queue
    database.save_state(_STATE_FILE, state)

    return f"Queued message for {name} — send after {send_after.strftime('%a %I:%M %p ET')}"


def run_message_queue() -> dict:
    """Process the message queue: send reminders for due messages, expire old ones.

    Returns {"reminded": N, "expired": N}.
    """
    state = database.load_state(_STATE_FILE, default=dict(_DEFAULT_STATE))
    queue = state.get("queue", [])

    now_utc = datetime.now(timezone.utc)
    reminded = 0
    expired = 0

    for entry in queue:
        if entry["status"] != "pending":
            continue

        # Check expiry first (7 days from queued_at)
        queued_at_str = entry.get("queued_at", "")
        if queued_at_str:
            try:
                queued_at = datetime.fromisoformat(queued_at_str)
                if queued_at.tzinfo is None:
                    queued_at = queued_at.replace(tzinfo=timezone.utc)
                if (now_utc - queued_at).days >= _EXPIRE_DAYS:
                    entry["status"] = "expired"
                    expired += 1
                    continue
            except (ValueError, TypeError):
                pass

        # Check if send_after has passed
        send_after_str = entry.get("send_after", "")
        if not send_after_str:
            continue

        try:
            send_after = datetime.fromisoformat(send_after_str)
            if send_after.tzinfo is None:
                send_after = send_after.replace(tzinfo=_ET)
        except (ValueError, TypeError):
            continue

        if now_utc >= send_after.astimezone(timezone.utc):
            profile_id = entry.get("profile_id", "")
            name = entry.get("name", "Unknown")
            draft = entry.get("message_draft", "")

            send_telegram(
                f"📨 Time to message {name}: {draft}\n"
                f"Open: linkedin.com/in/{profile_id}"
            )
            entry["status"] = "reminded"
            reminded += 1

    state["queue"] = queue
    database.save_state(_STATE_FILE, state)

    print(f"[message_queue] reminded={reminded} expired={expired}", flush=True)
    return {"reminded": reminded, "expired": expired}


def get_queue() -> list[dict]:
    """Return the current message queue."""
    state = database.load_state(_STATE_FILE, default=dict(_DEFAULT_STATE))
    return state.get("queue", [])
