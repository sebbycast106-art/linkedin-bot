"""
app_status_detector_service.py — Detect application status changes from inbox keywords.

Scans the application tracker for apps that have been "applied" for 3+ days and sends
a Telegram reminder asking the user to check status. Does NOT use Playwright.

Public interface:
    run_status_detection() -> dict  # {"detected": N, "suggested": N}
"""
from datetime import datetime, timezone, timedelta

import database
from application_tracker import get_applications
from telegram_service import send_telegram

_STATE_FILE = "status_detector_state.json"
_DEFAULT_STATE = {"last_run": "", "suggested_updates": []}

_STALE_DAYS = 3
_BATCH_SIZE = 10


def run_status_detection() -> dict:
    """Check for stale 'applied' apps and send Telegram reminders.

    Returns {"detected": N, "suggested": N} where detected is the number of
    stale apps found this run and suggested is the number of reminders sent.
    """
    state = database.load_state(_STATE_FILE, default=dict(_DEFAULT_STATE))
    already_suggested = set(state.get("suggested_updates", []))

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=_STALE_DAYS)

    applied_apps = get_applications(status_filter="applied")
    # Sort oldest first so we prioritize the most overdue
    applied_apps.sort(key=lambda a: a.get("applied_at", ""))

    detected = 0
    suggested = 0

    for app in applied_apps:
        if detected >= _BATCH_SIZE:
            break

        job_id = app.get("job_id", "")
        if not job_id:
            continue

        # Skip already-prompted apps
        if job_id in already_suggested:
            continue

        applied_at_str = app.get("applied_at", "")
        if not applied_at_str:
            continue

        try:
            applied_at = datetime.fromisoformat(applied_at_str)
            if applied_at.tzinfo is None:
                applied_at = applied_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue

        if applied_at >= cutoff:
            continue

        detected += 1

        company = app.get("company", "Unknown")
        title = app.get("title", "Unknown")
        days_ago = (now - applied_at).days

        send_telegram(
            f"🔍 Have you heard back from {company} — {title}? "
            f"(applied {days_ago} days ago)\n"
            f"Use /update {job_id} [status] to update."
        )
        already_suggested.add(job_id)
        suggested += 1

    state["last_run"] = now.isoformat()
    state["suggested_updates"] = list(already_suggested)
    database.save_state(_STATE_FILE, state)

    print(f"[status_detector] detected={detected} suggested={suggested}", flush=True)
    return {"detected": detected, "suggested": suggested}
