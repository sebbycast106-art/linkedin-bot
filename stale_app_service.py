"""
stale_app_service.py — Flag stale applications and send Telegram reminders.

Public interface:
    run_stale_check(stale_days=21) -> dict  # {"stale_count": N, "notified": bool}
"""
from datetime import datetime, timezone, timedelta
import application_tracker
from telegram_service import send_telegram


def run_stale_check(stale_days: int = 21) -> dict:
    """Find stale 'applied' apps (older than stale_days) and notify via Telegram."""
    apps = application_tracker.get_applications(status_filter="applied")
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = []

    for app in apps:
        applied_at_str = app.get("applied_at", "")
        if not applied_at_str:
            continue
        try:
            applied_at = datetime.fromisoformat(applied_at_str)
            if applied_at.tzinfo is None:
                applied_at = applied_at.replace(tzinfo=timezone.utc)
            if applied_at < cutoff:
                stale.append(app)
        except (ValueError, TypeError):
            continue

    notified = False
    if stale:
        lines = [f"📦 {len(stale)} stale application(s) (>{stale_days} days):"]
        for app in stale:
            days_ago = (datetime.now(timezone.utc) - datetime.fromisoformat(app["applied_at"])).days
            follow_up_label = "follow-up sent" if app.get("follow_up_sent") else "no follow-up yet"
            lines.append(f"  • {app['company']} — {app['title']} ({days_ago}d ago, {follow_up_label})")
        lines.append("\nConsider archiving via /update [job_id] archived")
        send_telegram("\n".join(lines))
        notified = True

    return {"stale_count": len(stale), "notified": notified}
