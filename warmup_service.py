"""
Warm-Up Mode — auto-ramps LinkedIn action limits over 3 weeks.
Week 1 (days 0-6):   50% of limits  (new account caution)
Week 2 (days 7-13):  75% of limits
Week 3+ (days 14+):  100% of limits (full speed)

Start date is recorded on first call and never resets automatically.
Can be manually reset via reset_warmup().
"""
import datetime
from zoneinfo import ZoneInfo
import database

_STATE_FILE = "warmup_state.json"

def _today() -> datetime.date:
    return datetime.datetime.now(ZoneInfo("America/New_York")).date()


def get_warmup_info() -> dict:
    state = database.load_state(_STATE_FILE, default={})
    start_str = state.get("start_date")

    if not start_str:
        # First call — record today as start
        start_str = _today().isoformat()
        state["start_date"] = start_str
        database.save_state(_STATE_FILE, state)

    start = datetime.date.fromisoformat(start_str)
    days_active = (_today() - start).days
    week_num = days_active // 7  # 0-indexed week

    if week_num == 0:
        multiplier = 0.50
        phase = "week_1"
        days_until_next = 7 - days_active
    elif week_num == 1:
        multiplier = 0.75
        phase = "week_2"
        days_until_next = 14 - days_active
    else:
        multiplier = 1.0
        phase = "full_speed"
        days_until_next = 0

    return {
        "active": multiplier < 1.0,
        "multiplier": multiplier,
        "pct": int(multiplier * 100),
        "phase": phase,
        "week_num": week_num + 1,
        "days_active": days_active,
        "start_date": start_str,
        "days_until_next": days_until_next,
    }


def get_multiplier() -> float:
    return get_warmup_info()["multiplier"]


def apply_limit(base_limit: int) -> int:
    """Apply warmup multiplier to a base daily limit. Always at least 1."""
    return max(1, int(base_limit * get_multiplier()))


def reset_warmup():
    """Reset warmup to start fresh from today. Call this after a ban/recovery."""
    database.save_state(_STATE_FILE, {"start_date": _today().isoformat()})


def skip_warmup():
    """Force full speed immediately (set start_date 21 days ago)."""
    past = (_today() - datetime.timedelta(days=21)).isoformat()
    database.save_state(_STATE_FILE, {"start_date": past})
