"""
daily_brief_service.py — Smart daily brief.

One Telegram message at the start of each day: new jobs, pending follow-ups,
recruiter replies, ghosts.

Run at 8:00 AM ET daily via cron.

Public interface:
    run_daily_brief() -> dict
"""
from datetime import datetime, timezone, timedelta
from database import load_state
import telegram_service as tg
import config


def _load_applications() -> list:
    """Load all applications from the application tracker state."""
    import database as _db
    state = _db.load_state("application_tracker_state.json", default={"applications": []})
    return state.get("applications", [])


def run_daily_brief():
    apps = _load_applications()
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)

    # 1. New jobs since yesterday (applied_at or seen_at within past 24h)
    new_today = []
    for app in apps:
        seen_at = app.get("applied_at") or app.get("seen_at")
        if not seen_at:
            continue
        try:
            dt = datetime.fromisoformat(seen_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= yesterday:
                new_today.append(app)
        except Exception:
            continue

    # 2. Applications awaiting response (applied, any age)
    awaiting = [a for a in apps if a.get("status") == "applied"]

    # 3. Ghosts (applied 14+ days, no response)
    ghosts = []
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
            if (now - dt).days >= 14:
                ghosts.append(app)
        except Exception:
            continue

    # 4. Active interviews
    interviews = [a for a in apps if a.get("status") == "interview"]

    # Load warmup info
    try:
        from warmup_service import get_warmup_info
        warmup = get_warmup_info()
        warmup_line = f"{warmup['pct']}% capacity (Week {warmup['week_num']}/3)"
    except Exception:
        warmup_line = "100%"

    lines = [
        ("NEW JOBS", str(len(new_today))),
        ("AWAITING REPLY", str(len(awaiting))),
        ("INTERVIEWS", str(len(interviews))),
        ("GHOSTS", f"{len(ghosts)} apps gone dark"),
        ("BOT CAPACITY", warmup_line),
        ("DATE", now.strftime("%A, %b %d")),
    ]

    tg.send_telegram(tg.block("DAILY BRIEF", lines))
    return {
        "new_jobs": len(new_today),
        "awaiting": len(awaiting),
        "ghosts": len(ghosts),
        "interviews": len(interviews),
    }
