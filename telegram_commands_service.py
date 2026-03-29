"""
telegram_commands_service.py — Parse and handle inbound Telegram bot commands.
"""
import time
import application_tracker

VALID_STATUSES = {"applied", "responded", "interview", "offer", "rejected"}

HELP_TEXT = """\
Available commands:
/status — Show all tracked applications
/applied [company] [title] — Log a new application (e.g. /applied Goldman Sachs Investment Banking Analyst)
/update [job_id] [status] — Update application status (applied/responded/interview/offer/rejected)
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

    if command == "/help":
        return HELP_TEXT

    return None
