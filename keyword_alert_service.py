"""
keyword_alert_service.py — Alert on jobs matching role-based keywords.

Public interface:
    check_keywords(jobs: list[dict]) -> list[dict]
    run_keyword_alerts() -> dict  # {"matched": N, "alerted": N}
    get_keywords() -> list[str]
    add_keyword(keyword: str) -> str
    remove_keyword(keyword: str) -> str
"""
import database
from telegram_service import send_telegram
import application_tracker

_STATE_FILE = "keyword_alerts_state.json"
_DEFAULT_KEYWORDS = [
    "quantitative", "analyst", "co-op", "spring 2027", "trading",
    "portfolio", "risk", "associate", "intern",
]
_MAX_ALERTED_IDS = 2000


def _load() -> dict:
    state = database.load_state(_STATE_FILE, default={})
    if "keywords" not in state:
        state["keywords"] = list(_DEFAULT_KEYWORDS)
    if "alerted_job_ids" not in state:
        state["alerted_job_ids"] = []
    return state


def _save(state: dict):
    # Cap alerted_job_ids at _MAX_ALERTED_IDS
    if len(state.get("alerted_job_ids", [])) > _MAX_ALERTED_IDS:
        state["alerted_job_ids"] = state["alerted_job_ids"][-_MAX_ALERTED_IDS:]
    database.save_state(_STATE_FILE, state)


def get_keywords() -> list:
    """Return the current keyword list."""
    return _load()["keywords"]


def add_keyword(keyword: str) -> str:
    """Add a keyword. Returns confirmation message."""
    kw = keyword.strip().lower()
    if not kw:
        return "Keyword cannot be empty."
    state = _load()
    if kw in [k.lower() for k in state["keywords"]]:
        return f"Keyword '{kw}' already exists."
    state["keywords"].append(kw)
    _save(state)
    return f"Added keyword: '{kw}'"


def remove_keyword(keyword: str) -> str:
    """Remove a keyword. Returns confirmation message."""
    kw = keyword.strip().lower()
    state = _load()
    original = state["keywords"]
    state["keywords"] = [k for k in original if k.lower() != kw]
    if len(state["keywords"]) == len(original):
        return f"Keyword '{kw}' not found."
    _save(state)
    return f"Removed keyword: '{kw}'"


def check_keywords(jobs: list) -> list:
    """Match jobs against keywords, skipping already-alerted. Returns matched jobs."""
    state = _load()
    keywords = [k.lower() for k in state["keywords"]]
    alerted_set = set(state["alerted_job_ids"])
    matched = []

    for job in jobs:
        job_id = job.get("job_id", "")
        if job_id in alerted_set:
            continue
        title = job.get("title", "").lower()
        company = job.get("company", "").lower()
        text = f"{title} {company}"
        if any(kw in text for kw in keywords):
            matched.append(job)

    return matched


def run_keyword_alerts() -> dict:
    """Load 'seen' apps, check keywords, send alerts. Returns {"matched": N, "alerted": N}."""
    jobs = application_tracker.get_applications(status_filter="seen")
    matched = check_keywords(jobs)

    alerted = 0
    if matched:
        state = _load()
        lines = [f"🔑 {len(matched)} job(s) match your keywords:"]
        for job in matched[:20]:  # cap message size
            lines.append(f"  • {job['company']} — {job['title']}")
            state["alerted_job_ids"].append(job["job_id"])
            alerted += 1
        if len(matched) > 20:
            lines.append(f"  ... and {len(matched) - 20} more")
        send_telegram("\n".join(lines))
        _save(state)

    return {"matched": len(matched), "alerted": alerted}
