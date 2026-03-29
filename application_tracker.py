"""
application_tracker.py — Track job applications and send follow-up reminders.
"""
from datetime import datetime, timezone, timedelta
import database

_STATE_FILE = "application_tracker_state.json"
_FOLLOW_UP_DAYS = 7  # remind to follow up after 7 days


def _load() -> dict:
    return database.load_state(_STATE_FILE, default={"applications": []})


def _save(state: dict):
    database.save_state(_STATE_FILE, state)


def add_application(job_id: str, company: str, title: str, url: str = "") -> str:
    """Record a job application. Returns confirmation message."""
    state = _load()
    apps = state["applications"]

    # Check duplicate
    if any(a["job_id"] == job_id for a in apps):
        return f"Already tracking application to {company} — {title}"

    apps.append({
        "job_id": job_id,
        "company": company,
        "title": title,
        "url": url,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "status": "applied",  # applied | responded | interview | offer | rejected
        "follow_up_sent": False,
    })
    # Cap at 200
    state["applications"] = apps[-200:]
    _save(state)
    return f"✅ Tracked: {company} — {title}"


def update_status(job_id: str, status: str) -> str:
    """Update application status. Returns confirmation or error."""
    valid = {"applied", "responded", "interview", "offer", "rejected"}
    if status not in valid:
        return f"Invalid status. Use: {', '.join(sorted(valid))}"

    state = _load()
    for app in state["applications"]:
        if app["job_id"] == job_id:
            app["status"] = status
            _save(state)
            return f"✅ Updated {app['company']} — {app['title']} → {status}"
    return f"Application {job_id} not found"


def get_applications(status_filter: str = None) -> list:
    """Return all applications, optionally filtered by status."""
    state = _load()
    apps = state["applications"]
    if status_filter:
        apps = [a for a in apps if a["status"] == status_filter]
    return sorted(apps, key=lambda a: a["applied_at"], reverse=True)


def check_follow_ups() -> list[str]:
    """Return Telegram messages for applications needing follow-up."""
    state = _load()
    now = datetime.now(timezone.utc)
    messages = []
    changed = False

    for app in state["applications"]:
        if app["status"] not in ("applied",):
            continue
        if app.get("follow_up_sent"):
            continue
        applied_dt = datetime.fromisoformat(app["applied_at"])
        days_ago = (now - applied_dt).days
        if days_ago >= _FOLLOW_UP_DAYS:
            messages.append(
                f"📬 Follow up on: {app['company']} — {app['title']}\n"
                f"Applied {days_ago} days ago. Status: {app['status']}\n"
                f"{app.get('url', '')}"
            )
            app["follow_up_sent"] = True
            changed = True

    if changed:
        _save(state)
    return messages


def format_applications_summary() -> str:
    """Return a formatted summary of all active applications."""
    apps = get_applications()
    if not apps:
        return "No applications tracked yet."

    active = [a for a in apps if a["status"] not in ("rejected",)]
    by_status = {}
    for a in active:
        by_status.setdefault(a["status"], []).append(a)

    lines = [f"📋 Applications ({len(active)} active, {len(apps)} total):"]
    for status in ["interview", "offer", "responded", "applied"]:
        if status in by_status:
            lines.append(f"\n{status.upper()} ({len(by_status[status])}):")
            for a in by_status[status][:5]:
                lines.append(f"  • {a['company']} — {a['title']}")
    return "\n".join(lines)
