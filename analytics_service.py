"""
analytics_service.py — Computes network and application analytics from bot state files.
"""
from collections import Counter
import database


def compute_analytics() -> dict:
    """Return a dict of all analytics metrics computed from state files."""
    conn_state = database.load_state("connection_tracker_state.json", default={})
    app_state = database.load_state("application_tracker_state.json", default={})
    recruiter_state = database.load_state("recruiter_state.json", default={})
    easy_apply_state = database.load_state("easy_apply_state.json", default={})
    connector_state = database.load_state("connector_state.json", default={})

    # --- Connection acceptance rate ---
    accepted = conn_state.get("accepted_count", 0)
    declined = conn_state.get("declined_count", 0)
    total_decided = accepted + declined
    acceptance_rate = accepted / total_decided if total_decided > 0 else 0.0

    # --- Application funnel ---
    applications = app_state.get("applications", [])
    status_counts = Counter(app.get("status", "unknown") for app in applications)

    seen = status_counts.get("seen", 0)
    applied = status_counts.get("applied", 0)
    responded = status_counts.get("responded", 0)
    interview = status_counts.get("interview", 0)
    offer = status_counts.get("offer", 0)
    rejected = status_counts.get("rejected", 0)

    # Conversion rates
    seen_to_applied = applied / seen if seen > 0 else 0.0
    applied_to_responded = responded / applied if applied > 0 else 0.0
    responded_to_interview = interview / responded if responded > 0 else 0.0
    interview_to_offer = offer / interview if interview > 0 else 0.0

    # --- Top companies ---
    company_counts = Counter(app.get("company", "Unknown") for app in applications)
    top_companies = company_counts.most_common(5)

    # --- Totals ---
    total_connections = len(connector_state.get("connected_ids", []))
    total_easy_applies = len(easy_apply_state.get("applied_ids", []))

    # --- Recruiter metrics ---
    pending_followup = recruiter_state.get("pending_followup", [])
    messaged_ids = recruiter_state.get("messaged_ids", [])
    total_recruiter_outreaches = len(pending_followup) + len(messaged_ids)
    recruiter_response_rate = (
        len(messaged_ids) / total_recruiter_outreaches
        if total_recruiter_outreaches > 0
        else 0.0
    )

    return {
        "acceptance_rate": round(acceptance_rate, 4),
        "accepted": accepted,
        "declined": declined,
        "funnel": {
            "seen": seen,
            "applied": applied,
            "responded": responded,
            "interview": interview,
            "offer": offer,
            "rejected": rejected,
        },
        "conversion_rates": {
            "seen_to_applied": round(seen_to_applied, 4),
            "applied_to_responded": round(applied_to_responded, 4),
            "responded_to_interview": round(responded_to_interview, 4),
            "interview_to_offer": round(interview_to_offer, 4),
        },
        "top_companies": top_companies,
        "total_connections": total_connections,
        "total_easy_applies": total_easy_applies,
        "total_recruiter_outreaches": total_recruiter_outreaches,
        "recruiter_response_rate": round(recruiter_response_rate, 4),
    }
