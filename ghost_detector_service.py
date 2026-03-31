"""
ghost_detector_service.py — Detect applications that have gone silent.

Apps that went silent: applied 14+ days ago, status still "applied", no response.

Public interface:
    run_ghost_detector() -> dict  # {"ghosts_found": N}
"""
from datetime import datetime, timezone, timedelta
from database import load_state, save_state
import telegram_service as tg
import config

GHOST_DAYS = 14  # days since apply with no response = ghost


def _load_applications():
    """Load all applications from the application tracker state."""
    import database as _db
    state = _db.load_state("application_tracker_state.json", default={"applications": []})
    return state.get("applications", [])


def run_ghost_detector():
    """
    Find applied jobs with no response after GHOST_DAYS.
    For each ghost: send a Telegram alert.
    State file: ghost_detector_state.json — tracks which job_ids already alerted.
    """
    state = load_state("ghost_detector_state.json", {"alerted_ids": [], "last_run": None})
    apps = _load_applications()

    now = datetime.now(timezone.utc)
    ghosts = []

    for app in apps:
        if app.get("status") != "applied":
            continue
        applied_at = app.get("applied_at")
        if not applied_at:
            continue
        try:
            applied_dt = datetime.fromisoformat(applied_at)
            if applied_dt.tzinfo is None:
                applied_dt = applied_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        days_since = (now - applied_dt).days
        if days_since >= GHOST_DAYS and app["job_id"] not in state["alerted_ids"]:
            ghosts.append({**app, "days_since": days_since})

    if not ghosts:
        state["last_run"] = now.isoformat()
        save_state("ghost_detector_state.json", state)
        return {"ghosts_found": 0}

    # Send one Telegram message per ghost
    for ghost in ghosts:
        lines = [
            ("COMPANY", ghost.get("company", "Unknown")),
            ("ROLE", ghost.get("title", "Unknown")),
            ("APPLIED", f"{ghost['days_since']} days ago"),
            ("STATUS", "No response — ghosted"),
            ("URL", ghost.get("url", "N/A")),
        ]
        tg.send_telegram(tg.block("GHOST DETECTED", lines))
        state["alerted_ids"].append(ghost["job_id"])

    # Cap alerted_ids at 2000
    state["alerted_ids"] = state["alerted_ids"][-2000:]
    state["last_run"] = now.isoformat()
    save_state("ghost_detector_state.json", state)

    return {"ghosts_found": len(ghosts)}


def get_ghost_count() -> int:
    """Return count of apps with status 'applied' and applied_at > 14 days ago."""
    apps = _load_applications()
    now = datetime.now(timezone.utc)
    count = 0
    for app in apps:
        if app.get("status") != "applied":
            continue
        applied_at = app.get("applied_at")
        if not applied_at:
            continue
        try:
            dt = datetime.fromisoformat(applied_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if (now - dt).days >= GHOST_DAYS:
                count += 1
        except Exception:
            continue
    return count
