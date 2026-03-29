"""
weekly_digest_service.py — Weekly summary of all LinkedIn bot activity.

Sent every Sunday. Calculates weekly deltas by comparing current state to
last Sunday's snapshot.

Public interface:
    run_weekly_digest() -> str  # returns the Telegram message sent
"""
from datetime import date
from collections import Counter
import database
import config
from telegram_service import send_telegram

_SNAPSHOT_FILE = "digest_state.json"

_ACTIVE_STATUSES = {"responded", "interview", "offer"}
_APPLIED_STATUSES = {"applied", "responded", "interview", "offer"}


def _load_snapshot() -> dict:
    return database.load_state(_SNAPSHOT_FILE, default={})


def _save_snapshot(snap: dict):
    database.save_state(_SNAPSHOT_FILE, snap)


def _get_current_totals() -> dict:
    connector_state = database.load_state("connector_state.json", default={})
    recruiter_state = database.load_state("recruiter_state.json", default={})
    job_scraper_state = database.load_state("job_scraper_state.json", default={})
    easy_apply_state = database.load_state("easy_apply_state.json", default={})
    application_tracker_state = database.load_state("application_tracker_state.json", default={})

    applications = application_tracker_state.get("applications", [])

    total_connections = len(connector_state.get("connected_ids", []))
    total_applied = sum(1 for a in applications if a.get("status") in _APPLIED_STATUSES)
    total_seen_jobs = len(job_scraper_state.get("seen_ids", []))
    total_recruiter_sent = (
        len(recruiter_state.get("pending_followup", []))
        + len(recruiter_state.get("messaged_ids", []))
    )
    total_recruiter_messaged = len(recruiter_state.get("messaged_ids", []))
    total_easy_applied = len(easy_apply_state.get("applied_ids", []))
    active_pipeline = sum(1 for a in applications if a.get("status") in _ACTIVE_STATUSES)

    company_counts = Counter(a.get("company", "") for a in applications if a.get("company"))
    top_companies = company_counts.most_common(3)

    return {
        "total_connections": total_connections,
        "total_applied": total_applied,
        "total_seen_jobs": total_seen_jobs,
        "total_recruiter_sent": total_recruiter_sent,
        "total_recruiter_messaged": total_recruiter_messaged,
        "total_easy_applied": total_easy_applied,
        "active_pipeline": active_pipeline,
        "top_companies": top_companies,
    }


def run_weekly_digest() -> str:
    today = date.today().isoformat()

    totals = _get_current_totals()
    snapshot = _load_snapshot()

    def delta(key: str) -> int:
        if not snapshot:
            return 0
        return totals.get(key, 0) - snapshot.get(key, 0)

    delta_connections = delta("total_connections")
    delta_applied = delta("total_applied")
    delta_seen = delta("total_seen_jobs")
    delta_recruiter_sent = delta("total_recruiter_sent")
    delta_easy_applied = delta("total_easy_applied")

    top_companies = totals["top_companies"]
    if top_companies:
        companies_lines = "\n".join(
            f"  \u2022 {company} ({count} apps)" for company, count in top_companies
        )
    else:
        companies_lines = "  \u2022 No applications yet"

    message = (
        f"\U0001f4ca Weekly LinkedIn Digest \u2014 {today}\n"
        "\n"
        "\U0001f91d Connections\n"
        f"  Total: {totals['total_connections']} (+{delta_connections} this week)\n"
        f"  Recruiter connects: {totals['total_recruiter_sent']} total, {totals['total_recruiter_messaged']} replied\n"
        "\n"
        "\U0001f4bc Job Pipeline\n"
        f"  Jobs seen: {totals['total_seen_jobs']} total (+{delta_seen} this week)\n"
        f"  Applied (Easy Apply): {totals['total_easy_applied']} (+{delta_easy_applied})\n"
        f"  Active pipeline: {totals['active_pipeline']} (responded/interview/offer)\n"
        "\n"
        "\U0001f4ec Top companies applied to:\n"
        f"{companies_lines}\n"
        "\n"
        f"\U0001f3af This week: {delta_connections} new connections, {delta_applied} applications, {delta_recruiter_sent} recruiter outreaches"
    )

    send_telegram(message)

    new_snapshot = {
        "snapshot_date": today,
        "total_connections": totals["total_connections"],
        "total_applied": totals["total_applied"],
        "total_seen_jobs": totals["total_seen_jobs"],
        "total_recruiter_sent": totals["total_recruiter_sent"],
        "total_recruiter_messaged": totals["total_recruiter_messaged"],
        "total_easy_applied": totals["total_easy_applied"],
    }
    _save_snapshot(new_snapshot)

    return message
