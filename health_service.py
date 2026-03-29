"""
health_service.py — Aggregate status across all services for the /internal/status endpoint.

Public interface:
    get_status() -> dict
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import database

_CONNECTOR_STATE      = "connector_state.json"
_RECRUITER_STATE      = "recruiter_state.json"
_PROFILE_VIEWS_STATE  = "profile_views_state.json"
_ENGAGEMENT_STATE     = "engagement_state.json"
_EASY_APPLY_STATE     = "easy_apply_state.json"
_INBOX_STATE          = "inbox_state.json"
_APP_TRACKER_STATE    = "application_tracker_state.json"
_JOB_SCRAPER_STATE    = "job_scraper_state.json"

_CONNECT_DAILY_LIMIT    = 20
_RECRUITER_DAILY_LIMIT  = 10
_PROFILE_VIEWS_LIMIT    = 10
_LIKES_LIMIT            = 50
_COMMENTS_LIMIT         = 20

_FOLLOWUP_DAYS = 5


def get_status() -> dict:
    try:
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

        connector   = database.load_state(_CONNECTOR_STATE,     default={})
        recruiter   = database.load_state(_RECRUITER_STATE,     default={})
        pv          = database.load_state(_PROFILE_VIEWS_STATE, default={})
        engagement  = database.load_state(_ENGAGEMENT_STATE,    default={})
        easy_apply  = database.load_state(_EASY_APPLY_STATE,    default={})
        inbox       = database.load_state(_INBOX_STATE,         default={})
        app_tracker = database.load_state(_APP_TRACKER_STATE,   default={})
        job_scraper = database.load_state(_JOB_SCRAPER_STATE,   default={})

        applications = app_tracker.get("applications", [])

        # by_status counts
        status_keys = ["seen", "applied", "responded", "interview", "offer", "rejected"]
        by_status = {k: 0 for k in status_keys}
        for app in applications:
            s = app.get("status", "")
            if s in by_status:
                by_status[s] += 1

        # pending followup: applied + not follow_up_sent + applied > 5 days ago
        cutoff = datetime.now(timezone.utc) - timedelta(days=_FOLLOWUP_DAYS)
        pending_followup_count = 0
        for app in applications:
            if app.get("status") != "applied":
                continue
            if app.get("follow_up_sent", True):
                continue
            applied_at_str = app.get("applied_at", "")
            if not applied_at_str:
                continue
            try:
                applied_at = datetime.fromisoformat(applied_at_str)
                # Make timezone-aware if naive
                if applied_at.tzinfo is None:
                    applied_at = applied_at.replace(tzinfo=timezone.utc)
                if applied_at < cutoff:
                    pending_followup_count += 1
            except (ValueError, TypeError):
                pass

        return {
            "today": today,
            "connections": {
                "total_all_time": len(connector.get("connected_ids", [])),
                "sent_today": connector.get("connects_today", 0) if connector.get("date") == today else 0,
                "daily_limit": _CONNECT_DAILY_LIMIT,
            },
            "recruiter": {
                "sent_today": recruiter.get("sent_today", 0) if recruiter.get("date") == today else 0,
                "daily_limit": _RECRUITER_DAILY_LIMIT,
                "pending_followup": len(recruiter.get("pending_followup", [])),
                "total_messaged": len(recruiter.get("messaged_ids", [])),
            },
            "profile_views": {
                "sent_today": pv.get("sent_today", 0) if pv.get("date") == today else 0,
                "daily_limit": _PROFILE_VIEWS_LIMIT,
            },
            "engagement": {
                "likes_today": engagement.get("likes", 0) if engagement.get("date") == today else 0,
                "comments_today": engagement.get("comments", 0) if engagement.get("date") == today else 0,
                "likes_limit": _LIKES_LIMIT,
                "comments_limit": _COMMENTS_LIMIT,
            },
            "jobs": {
                "total_seen": len(job_scraper.get("seen_ids", [])),
                "total_easy_applied": len(easy_apply.get("applied_ids", [])),
            },
            "applications": {
                "total": len(applications),
                "by_status": by_status,
                "pending_followup": pending_followup_count,
            },
            "inbox": {
                "seen_threads": len(inbox.get("seen_thread_ids", [])),
            },
        }

    except Exception as e:
        return {"error": str(e)}
