"""
interview_prep_service.py — Generate and send interview prep packages via Claude.

When an application status changes to "interview", this service generates a
concise prep package and sends it to Telegram.

Public interface:
    run_interview_prep_check() -> dict   {"prepped": N}
    generate_prep_package(title, company) -> str
"""
import anthropic
import config
import database
import application_tracker
from telegram_service import send_telegram

_STATE_FILE = "interview_prep_state.json"


def _load() -> dict:
    return database.load_state(_STATE_FILE, default={"prepped_ids": []})


def _save(state: dict):
    database.save_state(_STATE_FILE, state)


def generate_prep_package(title: str, company: str) -> str:
    """Call Claude to generate a concise interview prep message.

    Returns a formatted string. Never returns None — falls back to a basic
    string on any error.
    """
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"Generate a concise interview prep message for a Northeastern sophomore "
            f"interviewing for {title} at {company}. Include: 3 likely interview questions "
            f"with brief answer tips, 1 key thing to research about the company, 1 smart "
            f"question to ask the interviewer. Format for Telegram (use emojis, keep it tight)."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        result = response.content[0].text.strip()
        return result if result else f"Interview prep for {title} at {company}: Research the company, prepare examples, and ask thoughtful questions."
    except Exception as e:
        print(f"[interview_prep_service] generate_prep_package error: {e}", flush=True)
        return f"Interview prep for {title} at {company}: Research the company, prepare examples, and ask thoughtful questions."


def run_interview_prep_check() -> dict:
    """Find applications with status='interview' that haven't been prepped yet.

    For each new interview-status application, generates a prep package and
    sends it to Telegram. Returns {"prepped": N}.
    """
    state = _load()
    prepped_ids: list = state.get("prepped_ids", [])

    interview_apps = application_tracker.get_applications(status_filter="interview")
    new_apps = [a for a in interview_apps if a["job_id"] not in prepped_ids]

    count = 0
    for app in new_apps:
        job_id = app["job_id"]
        title = app.get("title", "")
        company = app.get("company", "")

        prep = generate_prep_package(title, company)
        message = (
            f"🎯 Interview Prep: {title} @ {company}\n\n{prep}"
        )
        send_telegram(message)

        prepped_ids.append(job_id)
        count += 1

    if count > 0:
        state["prepped_ids"] = prepped_ids
        _save(state)

    return {"prepped": count}
