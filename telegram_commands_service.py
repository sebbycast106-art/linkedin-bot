"""
telegram_commands_service.py — Parse and handle inbound Telegram bot commands.
"""
import os
import time
import requests
import application_tracker

VALID_STATUSES = {"applied", "responded", "interview", "offer", "rejected", "archived"}

_TRIGGER_MAP = {
    "scraper": "run-job-scraper",
    "engagement": "run-engagement",
    "connector": "run-connector",
    "recruiter": "run-recruiter",
    "followup": "run-recruiter-followup",
    "apply": "run-easy-apply",
    "views": "run-profile-views",
    "inbox": "run-inbox-check",
    "watchlist": "run-watchlist",
    "digest": "run-weekly-digest",
    "acceptance": "run-acceptance-check",
    "prep": "run-interview-prep",
    "alumni": "run-alumni-connector",
    "stale": "run-stale-check",
    "keywordalerts": "run-keyword-alerts",
    "notifications": "flush-notifications",
    "statusdetector": "run-status-detector",
    "messagequeue": "run-message-queue",
    "warmth": "warmth-scores",
    "skillmatch": "run-skill-match",
}

HELP_TEXT = """\
Available commands:
/status — Show all tracked applications
/applied [company] [title] — Log a new application (e.g. /applied Goldman Sachs Investment Banking Analyst)
/update [job_id] [status] — Update application status (applied/responded/interview/offer/rejected/archived)
/trigger [service] — Manually trigger a bot service (e.g. /trigger scraper)
/queue — Show pending message queue and next send window
/keywords — Show keyword alert list
/keywords add [word] — Add a keyword alert
/keywords remove [word] — Remove a keyword alert
/analytics — Show network and application analytics
/skills — Show skill profile. /skills add [skill] or /skills remove [skill]
/warm — Show top 10 warmest connections
/help — Show this help message\
"""


def _make_job_id(company: str) -> str:
    suffix = str(int(time.time()))[-6:]
    slug = company[:10].lower().replace(" ", "_")
    return f"{slug}_{suffix}"


def handle_telegram_command(text: str):
    """Parse a Telegram message and return a reply string, or None if unrecognized."""
    if not text or not text.startswith("/"):
        return None

    parts = text.strip().split(None, 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command == "/status":
        return application_tracker.format_applications_summary()

    if command == "/applied":
        if not args:
            return "Usage: /applied [company] [title]"
        words = args.split(None, 1)
        company = words[0]
        title = words[1] if len(words) > 1 else ""
        job_id = _make_job_id(company)
        application_tracker.add_application(job_id, company, title, status="applied")
        return f"✅ Logged: {company} – {title}"

    if command == "/update":
        words = args.split()
        if len(words) < 2:
            return "Usage: /update [job_id] [status]"
        job_id = words[0]
        new_status = words[1].lower()
        if new_status not in VALID_STATUSES:
            return f"Invalid status. Valid options: {', '.join(sorted(VALID_STATUSES))}"
        result = application_tracker.update_status(job_id, new_status)
        return result

    if command == "/queue":
        return _handle_queue()

    if command == "/keywords":
        return _handle_keywords(args)

    if command == "/analytics":
        return _handle_analytics()

    if command == "/skills":
        return _handle_skills(args)

    if command == "/warm":
        return _handle_warm()

    if command == "/trigger":
        return _handle_trigger(args)

    if command == "/help":
        return HELP_TEXT

    return None


def _handle_queue() -> str:
    """Show pending message queue status and next send window."""
    from message_scheduler_service import get_queue, _next_optimal_window, _ET
    from datetime import datetime

    queue = get_queue()
    pending = [e for e in queue if e.get("status") == "pending"]

    if not pending:
        return "📨 Message queue is empty."

    now_et = datetime.now(_ET)
    next_window = _next_optimal_window(now_et)

    lines = [f"📨 Message Queue ({len(pending)} pending):"]
    for entry in pending[:5]:
        name = entry.get("name", "Unknown")
        send_after = entry.get("send_after", "")
        lines.append(f"  • {name} — send after {send_after[:16]}")

    if len(pending) > 5:
        lines.append(f"  ... and {len(pending) - 5} more")

    lines.append(f"\nNext send window: {next_window.strftime('%a %I:%M %p ET')}")
    return "\n".join(lines)


def _handle_keywords(args: str) -> str:
    """Handle /keywords command: list, add, or remove keywords."""
    from keyword_alert_service import get_keywords, add_keyword, remove_keyword

    if not args:
        keywords = get_keywords()
        if not keywords:
            return "No keywords configured."
        return "🔑 Alert keywords:\n" + "\n".join(f"  • {k}" for k in keywords)

    parts = args.strip().split(None, 1)
    action = parts[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ""

    if action == "add":
        if not value:
            return "Usage: /keywords add [keyword]"
        return add_keyword(value)

    if action == "remove":
        if not value:
            return "Usage: /keywords remove [keyword]"
        return remove_keyword(value)

    return "Usage: /keywords [add|remove] [keyword]"


def _handle_skills(args: str) -> str:
    """Handle /skills command: show, add, or remove skills."""
    from skill_match_service import get_skill_profile, update_skill_profile

    if not args:
        profile = get_skill_profile()
        skills = profile.get("skills", [])
        roles = profile.get("target_roles", [])
        lines = [
            "🎯 Skill Profile:",
            f"  Skills ({len(skills)}): {', '.join(skills)}",
            f"  Target roles ({len(roles)}): {', '.join(roles)}",
        ]
        return "\n".join(lines)

    parts = args.strip().split(None, 1)
    action = parts[0].lower()
    value = parts[1].strip() if len(parts) > 1 else ""

    if action == "add":
        if not value:
            return "Usage: /skills add [skill]"
        profile = get_skill_profile()
        skills = profile.get("skills", [])
        if value.lower() in [s.lower() for s in skills]:
            return f"Skill '{value}' already exists."
        skills.append(value)
        update_skill_profile(skills=skills)
        return f"✅ Added skill: {value}"

    if action == "remove":
        if not value:
            return "Usage: /skills remove [skill]"
        profile = get_skill_profile()
        skills = profile.get("skills", [])
        new_skills = [s for s in skills if s.lower() != value.lower()]
        if len(new_skills) == len(skills):
            return f"Skill '{value}' not found."
        update_skill_profile(skills=new_skills)
        return f"✅ Removed skill: {value}"

    return "Usage: /skills [add|remove] [skill]"


def _handle_warm() -> str:
    """Handle /warm command: show top 10 warmest connections."""
    from warmth_scorer_service import get_warmth_scores

    scores = get_warmth_scores(min_score=1)
    if not scores:
        return "No warmth data yet."

    lines = ["🔥 Top 10 Warmest Connections:"]
    for entry in scores[:10]:
        name = entry.get("name", entry["profile_id"])
        score = entry["score"]
        signals = entry.get("signals", {})
        signal_str = ", ".join(f"{k}={v}" for k, v in signals.items())
        lines.append(f"  {score}pts — {name} ({signal_str})")

    return "\n".join(lines)


def _handle_analytics() -> str:
    """Format analytics metrics as readable Telegram text."""
    from analytics_service import compute_analytics
    data = compute_analytics()
    funnel = data["funnel"]
    rates = data["conversion_rates"]

    lines = [
        "📊 Network & Application Analytics",
        "",
        f"🤝 Connections: {data['total_connections']} sent",
        f"   Acceptance rate: {data['acceptance_rate']:.1%} ({data['accepted']} accepted, {data['declined']} declined)",
        "",
        f"📝 Easy Applies: {data['total_easy_applies']}",
        f"👔 Recruiter outreaches: {data['total_recruiter_outreaches']}",
        f"   Response rate: {data['recruiter_response_rate']:.1%}",
        "",
        "📈 Application Funnel:",
        f"   Seen: {funnel['seen']}",
        f"   Applied: {funnel['applied']}",
        f"   Responded: {funnel['responded']}",
        f"   Interview: {funnel['interview']}",
        f"   Offer: {funnel['offer']}",
        f"   Rejected: {funnel['rejected']}",
        "",
        "🔄 Conversion Rates:",
        f"   Seen → Applied: {rates['seen_to_applied']:.1%}",
        f"   Applied → Responded: {rates['applied_to_responded']:.1%}",
        f"   Responded → Interview: {rates['responded_to_interview']:.1%}",
        f"   Interview → Offer: {rates['interview_to_offer']:.1%}",
    ]

    if data["top_companies"]:
        lines.append("")
        lines.append("🏢 Top Companies:")
        for company, count in data["top_companies"]:
            lines.append(f"   {company}: {count}")

    return "\n".join(lines)


def _handle_trigger(args: str) -> str:
    """Trigger a bot service via its internal endpoint."""
    available = ", ".join(sorted(_TRIGGER_MAP))

    if not args:
        return f"Usage: /trigger [service]\nAvailable services: {available}"

    service = args.strip().split()[0].lower()
    if service not in _TRIGGER_MAP:
        return f"Unknown service '{service}'.\nAvailable services: {available}"

    endpoint = _TRIGGER_MAP[service]
    secret = os.environ.get("SCHEDULER_SECRET", "")
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")

    if domain:
        base_url = f"https://{domain}"
    else:
        base_url = "http://localhost:5000"

    url = f"{base_url}/internal/{endpoint}?secret={secret}"

    try:
        resp = requests.post(url, timeout=15)
        if resp.ok:
            return f"Triggered '{service}' successfully."
        else:
            return f"Failed to trigger '{service}': HTTP {resp.status_code}"
    except requests.RequestException as exc:
        return f"Failed to trigger '{service}': {exc}"
