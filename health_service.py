"""
health_service.py — Aggregate status across all services for the /internal/status endpoint.

Public interface:
    get_status() -> dict
"""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import database
from warmup_service import get_warmup_info

_CONNECTOR_STATE      = "connector_state.json"
_RECRUITER_STATE      = "recruiter_state.json"
_PROFILE_VIEWS_STATE  = "profile_views_state.json"
_ENGAGEMENT_STATE     = "engagement_state.json"
_EASY_APPLY_STATE     = "easy_apply_state.json"
_INBOX_STATE          = "inbox_state.json"
_APP_TRACKER_STATE    = "application_tracker_state.json"
_JOB_SCRAPER_STATE    = "job_scraper_state.json"
_KEYWORD_ALERTS_STATE = "keyword_alerts_state.json"
_NOTIFICATION_STATE   = "notification_buffer_state.json"
_STATUS_DETECTOR_STATE = "status_detector_state.json"
_MESSAGE_QUEUE_STATE   = "message_queue_state.json"
_SKILL_PROFILE_STATE   = "skill_profile_state.json"
_WARMTH_SCORES_STATE   = "warmth_scores_state.json"

_CONNECT_DAILY_LIMIT    = 20
_CONNECT_WEEKLY_LIMIT   = 100
_RECRUITER_DAILY_LIMIT  = 10
_PROFILE_VIEWS_LIMIT    = 80
_LIKES_LIMIT            = 50
_COMMENTS_LIMIT         = 20
_MESSAGES_DAILY_LIMIT   = 20

_ALUMNI_STATE = "alumni_connector_state.json"

_FOLLOWUP_DAYS = 5
_GHOST_DAYS = 14


def _count_ghosts(applications: list) -> int:
    """Count apps with status 'applied' and applied_at older than _GHOST_DAYS days."""
    now = datetime.now(timezone.utc)
    count = 0
    for app in applications:
        if app.get("status") != "applied":
            continue
        applied_at_str = app.get("applied_at", "")
        if not applied_at_str:
            continue
        try:
            applied_at = datetime.fromisoformat(applied_at_str)
            if applied_at.tzinfo is None:
                applied_at = applied_at.replace(tzinfo=timezone.utc)
            if (now - applied_at).days >= _GHOST_DAYS:
                count += 1
        except (ValueError, TypeError):
            pass
    return count


def get_status() -> dict:
    try:
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()

        connector   = database.load_state(_CONNECTOR_STATE,     default={})
        alumni      = database.load_state(_ALUMNI_STATE,        default={})
        recruiter   = database.load_state(_RECRUITER_STATE,     default={})
        pv          = database.load_state(_PROFILE_VIEWS_STATE, default={})
        engagement  = database.load_state(_ENGAGEMENT_STATE,    default={})
        easy_apply  = database.load_state(_EASY_APPLY_STATE,    default={})
        inbox       = database.load_state(_INBOX_STATE,         default={})
        app_tracker = database.load_state(_APP_TRACKER_STATE,   default={})
        job_scraper = database.load_state(_JOB_SCRAPER_STATE,   default={})
        kw_alerts   = database.load_state(_KEYWORD_ALERTS_STATE, default={})
        notif_buffer = database.load_state(_NOTIFICATION_STATE,  default={})
        status_det  = database.load_state(_STATUS_DETECTOR_STATE, default={})
        msg_queue   = database.load_state(_MESSAGE_QUEUE_STATE,   default={})
        skill_prof  = database.load_state(_SKILL_PROFILE_STATE,   default={})
        warmth      = database.load_state(_WARMTH_SCORES_STATE,   default={})

        applications = app_tracker.get("applications", [])

        # by_status counts
        status_keys = ["seen", "applied", "responded", "interview", "offer", "rejected", "archived"]
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

        # ── Safety meter data ──────────────────────────────────────────────
        connects_today = (
            (connector.get("connects_today", 0) if connector.get("date") == today else 0)
            + (alumni.get("sent_today", 0) if alumni.get("date") == today else 0)
        )
        connects_this_week = (
            connector.get("sent_this_week", 0)
            + alumni.get("sent_this_week", 0)
        )
        messages_today = recruiter.get("sent_today", 0) if recruiter.get("date") == today else 0
        views_today = pv.get("sent_today", 0) if pv.get("date") == today else 0
        likes_today = engagement.get("likes", 0) if engagement.get("date") == today else 0

        def _pct(val, limit):
            return (val / limit * 100) if limit else 0

        pcts = [
            _pct(connects_today, _CONNECT_DAILY_LIMIT),
            _pct(connects_this_week, _CONNECT_WEEKLY_LIMIT),
            _pct(messages_today, _MESSAGES_DAILY_LIMIT),
            _pct(views_today, _PROFILE_VIEWS_LIMIT),
            _pct(likes_today, _LIKES_LIMIT),
        ]
        max_pct = max(pcts) if pcts else 0
        if max_pct >= 90:
            risk_level = "danger"
        elif max_pct >= 70:
            risk_level = "caution"
        else:
            risk_level = "safe"

        from connector_service import get_response_rate
        response_rate = get_response_rate()

        return {
            "today": today,
            "response_rate": response_rate,
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
            "keyword_alerts": {
                "keyword_count": len(kw_alerts.get("keywords", [])),
                "alerted_count": len(kw_alerts.get("alerted_job_ids", [])),
            },
            "notification_buffer": {
                "buffer_size": len(notif_buffer.get("buffer", [])),
                "last_flush": notif_buffer.get("last_flush", ""),
            },
            "status_detector": {
                "last_run": status_det.get("last_run", ""),
                "suggested_count": len(status_det.get("suggested_updates", [])),
            },
            "message_queue": {
                "queue_size": len(msg_queue.get("queue", [])),
                "pending": len([e for e in msg_queue.get("queue", []) if e.get("status") == "pending"]),
            },
            "skill_match": {
                "skill_count": len(skill_prof.get("skills", [])),
            },
            "warmth": {
                "total_tracked": len(warmth.get("scores", {})),
                "top_3": sorted(
                    [
                        {"name": v.get("name", k), "score": v.get("score", 0)}
                        for k, v in warmth.get("scores", {}).items()
                    ],
                    key=lambda x: x["score"],
                    reverse=True,
                )[:3],
            },
            "safety": {
                "connections": {
                    "today": connects_today,
                    "today_limit": _CONNECT_DAILY_LIMIT,
                    "week": connects_this_week,
                    "week_limit": _CONNECT_WEEKLY_LIMIT,
                },
                "messages": {
                    "today": messages_today,
                    "today_limit": _MESSAGES_DAILY_LIMIT,
                },
                "profile_views": {
                    "today": views_today,
                    "today_limit": _PROFILE_VIEWS_LIMIT,
                },
                "likes": {
                    "today": likes_today,
                    "today_limit": _LIKES_LIMIT,
                },
                "risk_level": risk_level,
                "ghost_count": _count_ghosts(applications),
            },
            "warmup": get_warmup_info(),
        }

    except Exception as e:
        return {"error": str(e)}
