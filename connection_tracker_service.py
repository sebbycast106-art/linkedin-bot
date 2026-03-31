"""
connection_tracker_service.py — Track pending connection requests and detect acceptances.

State file: connection_tracker_state.json
{
  "pending": [
    {"profile_id": "jane-doe-123", "name": "Jane", "sent_at": 1711670400}
  ],
  "accepted_count": 0,
  "declined_count": 0,
  "last_check": "2026-03-29"
}

Public interface:
    add_pending_connection(profile_id, name) -> None
    run_acceptance_check(session) -> dict   # {"accepted": N, "still_pending": M}
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import database
from linkedin_session import random_delay
from telegram_service import send_telegram

_STATE_FILE = "connection_tracker_state.json"
_MAX_PENDING = 500
_MAX_CHECKS_PER_RUN = 20
_MIN_AGE_SECONDS = 86400  # 24 hours


def _default_state() -> dict:
    return {
        "pending": [],
        "accepted_count": 0,
        "declined_count": 0,
        "last_check": "",
    }


def _load_state() -> dict:
    return database.load_state(_STATE_FILE, default=_default_state())


def _save_state(state: dict) -> None:
    database.save_state(_STATE_FILE, state)


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def add_pending_connection(profile_id: str, name: str) -> None:
    """Add a newly-sent connection request to the pending list."""
    state = _load_state()
    pending = state.get("pending", [])
    pending.append({
        "profile_id": profile_id,
        "name": name,
        "sent_at": int(time.time()),
    })
    # Keep most recent _MAX_PENDING entries only
    if len(pending) > _MAX_PENDING:
        pending = pending[-_MAX_PENDING:]
    state["pending"] = pending
    _save_state(state)


def run_acceptance_check(session) -> dict:
    """
    Visit profiles older than 24 hours and check whether the connection was accepted.

    Returns {"accepted": N, "still_pending": M}.
    """
    state = _load_state()
    now = time.time()
    pending = state.get("pending", [])

    still_pending = []
    to_check = []

    for entry in pending:
        age = now - entry.get("sent_at", 0)
        if age < _MIN_AGE_SECONDS:
            # Too recent — don't check yet
            still_pending.append(entry)
        else:
            to_check.append(entry)

    # Cap at 20 per run to avoid rate limits
    deferred = to_check[_MAX_CHECKS_PER_RUN:]
    to_check = to_check[:_MAX_CHECKS_PER_RUN]

    accepted = 0

    page = session.new_page()
    try:
        for entry in to_check:
            profile_id = entry["profile_id"]
            try:
                page.goto(
                    f"https://www.linkedin.com/in/{profile_id}/", timeout=20000
                )
                random_delay(2, 4)

                msg_btn = page.query_selector("button[aria-label*='Message']")
                connect_btn = page.query_selector(
                    "button[aria-label*='Connect'], button[aria-label='Connect']"
                )

                if msg_btn:
                    # Connection was accepted
                    state["accepted_count"] = state.get("accepted_count", 0) + 1
                    accepted += 1
                    try:
                        from warmth_scorer_service import record_signal
                        record_signal(profile_id, entry.get("name", ""), "connection_accepted")
                    except Exception:
                        pass
                    # Update response rate stats in connector_state.json
                    try:
                        connector_state = database.load_state("connector_state.json", {})
                        connector_state["total_accepted"] = connector_state.get("total_accepted", 0) + 1
                        # Update matching daily_stats entry for the day the request was sent
                        sent_date = None
                        if entry.get("sent_at"):
                            from datetime import date
                            import time as _time
                            sent_date = date.fromtimestamp(entry["sent_at"]).isoformat()
                        daily_stats = connector_state.get("daily_stats", [])
                        for day in daily_stats:
                            if sent_date and day.get("date") == sent_date:
                                day["accepted"] = day.get("accepted", 0) + 1
                                break
                        connector_state["daily_stats"] = daily_stats
                        database.save_state("connector_state.json", connector_state)
                    except Exception as e:
                        print(f"[connection_tracker] response rate update error: {e}", flush=True)
                    print(
                        f"[connection_tracker] accepted: {entry.get('name', profile_id)}",
                        flush=True,
                    )
                elif connect_btn:
                    # Connection was declined or withdrawn — they removed us
                    state["declined_count"] = state.get("declined_count", 0) + 1
                    print(
                        f"[connection_tracker] declined/withdrew: {entry.get('name', profile_id)}",
                        flush=True,
                    )
                else:
                    # Unknown state (private profile, 404, etc.) — keep pending
                    still_pending.append(entry)

            except Exception as e:
                print(
                    f"[connection_tracker] error checking {profile_id}: {e}",
                    flush=True,
                )
                still_pending.append(entry)

            random_delay(2, 4)
    finally:
        page.close()

    # Entries that exceeded the per-run cap go back to pending for next run
    still_pending.extend(deferred)

    state["pending"] = still_pending
    state["last_check"] = _today()
    _save_state(state)

    if accepted > 0:
        send_telegram(
            f"🤝 {accepted} new connections accepted (total: {state['accepted_count']})"
        )

    print(
        f"[connection_tracker] accepted={accepted}, still_pending={len(still_pending)}",
        flush=True,
    )
    return {"accepted": accepted, "still_pending": len(still_pending)}
