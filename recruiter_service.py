"""
recruiter_service.py — Find recruiters at target companies, connect, then follow up after accept.

Daily limit: 10 recruiter connection requests/day (separate from connector_service).

State file: recruiter_state.json
{
  "date": "2026-03-28",
  "sent_today": 3,
  "pending_followup": [
    {"profile_id": "john-smith-123", "name": "John", "company": "Fidelity", "sent_at": 1711670400}
  ],
  "messaged_ids": ["john-smith-123"]
}

Public interface:
    run_recruiter_outreach(session) -> dict   # {"sent": N}
    run_followup_check(session) -> dict       # {"messaged": N}
"""
import time
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

from linkedin_session import random_delay
import database
import ai_service
import config
from telegram_service import send_telegram
from warmup_service import apply_limit

_STATE_FILE = "recruiter_state.json"
_DAILY_LIMIT = apply_limit(10)
_MAX_MESSAGED_IDS = 2000

_FALLBACK_NOTE = (
    "Hi, I'm a Northeastern sophomore interested in finance/fintech co-ops. "
    "I'd love to connect and learn more about opportunities at your firm!"
)

_TARGET_SEARCHES = [
    "recruiter Fidelity",
    "recruiter BlackRock",
    "recruiter Goldman Sachs",
    "recruiter JPMorgan",
    "talent acquisition fintech",
    "recruiter Citadel",
    "recruiter Jane Street",
    "campus recruiter Boston finance",
    "university recruiting finance",
    "recruiter asset management",
]


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _load_state() -> dict:
    return database.load_state(
        _STATE_FILE,
        default={
            "date": _today(),
            "sent_today": 0,
            "pending_followup": [],
            "messaged_ids": [],
        },
    )


def _save_state(state: dict):
    database.save_state(_STATE_FILE, state)


def run_recruiter_outreach(session) -> dict:
    """Search for recruiters, send connection requests up to daily limit."""
    state = _load_state()

    # Check daily limit
    if state.get("date") == _today() and state.get("sent_today", 0) >= _DAILY_LIMIT:
        print("[recruiter] daily limit already reached", flush=True)
        return {"sent": 0}

    # Reset daily count if date changed
    if state.get("date") != _today():
        state["date"] = _today()
        state["sent_today"] = 0

    pending_ids = {entry["profile_id"] for entry in state.get("pending_followup", [])}
    messaged_ids = set(state.get("messaged_ids", []))
    sent = 0

    page = session.new_page()
    try:
        for query in _TARGET_SEARCHES:
            if state.get("sent_today", 0) >= _DAILY_LIMIT:
                print("[recruiter] daily limit reached", flush=True)
                break

            url = (
                "https://www.linkedin.com/search/results/people/"
                f"?keywords={urllib.parse.quote(query)}&network=S"
            )
            try:
                page.goto(url, timeout=20000)
                random_delay(3, 5)

                results = page.query_selector_all(".reusable-search__result-container")[:5]
                for result in results:
                    if state.get("sent_today", 0) >= _DAILY_LIMIT:
                        break
                    try:
                        name_el = result.query_selector(
                            ".entity-result__title-text a span[aria-hidden='true']"
                        )
                        title_el = result.query_selector(".entity-result__primary-subtitle")
                        link_el = result.query_selector("a.app-aware-link[href*='/in/']")

                        if not name_el or not link_el:
                            continue

                        name = name_el.inner_text().strip()
                        title = (title_el.inner_text() if title_el else "").strip()
                        href = link_el.get_attribute("href") or ""
                        profile_id = (
                            href.split("/in/")[1].split("/")[0].split("?")[0]
                            if "/in/" in href
                            else ""
                        )

                        if not profile_id:
                            continue
                        if profile_id in pending_ids or profile_id in messaged_ids:
                            continue

                        connect_btn = result.query_selector("button[aria-label*='Connect']")
                        if not connect_btn:
                            continue

                        company_from_title = (
                            title.split(" at ")[-1] if " at " in title else ""
                        )
                        note = ai_service.generate_connection_message(
                            name, title, company_from_title, headline=title
                        ) or _FALLBACK_NOTE

                        connect_btn.click()
                        random_delay(1, 2)

                        add_note_btn = page.query_selector("button[aria-label='Add a note']")
                        if add_note_btn and note:
                            add_note_btn.click()
                            random_delay(0.5, 1)
                            note_box = page.query_selector("textarea#custom-message")
                            if note_box:
                                note_box.fill(note)
                                random_delay(0.5, 1)

                        send_btn = page.query_selector(
                            "button[aria-label='Send now'], button[aria-label='Send invitation']"
                        )
                        if send_btn:
                            send_btn.click()
                            random_delay(2, 4)

                            state.setdefault("pending_followup", []).append({
                                "profile_id": profile_id,
                                "name": name,
                                "company": company_from_title,
                                "sent_at": time.time(),
                            })
                            pending_ids.add(profile_id)
                            state["sent_today"] = state.get("sent_today", 0) + 1
                            sent += 1
                            _save_state(state)
                            print(f"[recruiter] connected: {name}", flush=True)
                        else:
                            dismiss = page.query_selector("button[aria-label='Dismiss']")
                            if dismiss:
                                dismiss.click()

                        random_delay(8, 15)
                    except Exception as e:
                        print(f"[recruiter] person error: {e}", flush=True)

            except Exception as e:
                print(f"[recruiter] search error: {e}", flush=True)
    finally:
        page.close()
        _save_state(state)

    send_telegram(f"🤝 Recruiter outreach: {sent} connection requests sent")
    print(f"[recruiter] sent {sent} requests", flush=True)
    return {"sent": sent}


def run_followup_check(session) -> dict:
    """Visit pending profiles; if they accepted (Message button visible), send follow-up."""
    state = _load_state()
    now = time.time()
    pending = state.get("pending_followup", [])
    messaged_ids = state.get("messaged_ids", [])
    still_pending = []
    messaged = 0

    page = session.new_page()
    try:
        for entry in pending:
            if now - entry.get("sent_at", 0) < 86400:
                still_pending.append(entry)
                continue

            profile_id = entry["profile_id"]
            name = entry.get("name", "")
            company = entry.get("company", "")

            try:
                page.goto(
                    f"https://www.linkedin.com/in/{profile_id}/", timeout=20000
                )
                random_delay(2, 3)

                msg_btn = page.query_selector("button[aria-label*='Message']")
                if msg_btn:
                    followup = ai_service.generate_recruiter_followup_message(name, company)
                    if followup:
                        msg_btn.click()
                        random_delay(1, 2)
                        msg_box = page.query_selector(".msg-form__contenteditable")
                        if msg_box:
                            msg_box.fill(followup)
                            random_delay(0.5, 1)
                            send_btn = page.query_selector("button.msg-form__send-button")
                            if send_btn:
                                send_btn.click()
                                random_delay(1, 2)
                                messaged_ids.append(profile_id)
                                messaged += 1
                                print(f"[recruiter] follow-up sent to {name}", flush=True)
                            else:
                                # Send button missing — keep pending for retry
                                still_pending.append(entry)
                        else:
                            # Message box missing — keep pending for retry
                            still_pending.append(entry)
                    else:
                        # AI failed — keep pending so it will be retried next run
                        print(f"[recruiter] AI failed for {name}, will retry", flush=True)
                        still_pending.append(entry)
                else:
                    # Not yet accepted — keep pending
                    still_pending.append(entry)

                random_delay(5, 10)
            except Exception as e:
                print(f"[recruiter] followup error for {profile_id}: {e}", flush=True)
                still_pending.append(entry)
    finally:
        page.close()

    state["pending_followup"] = still_pending
    # Trim oldest entries to keep the file bounded
    if len(messaged_ids) > _MAX_MESSAGED_IDS:
        messaged_ids = messaged_ids[-_MAX_MESSAGED_IDS:]
    state["messaged_ids"] = messaged_ids
    _save_state(state)

    send_telegram(f"💬 Recruiter follow-ups sent: {messaged}")
    print(f"[recruiter] follow-ups sent: {messaged}", flush=True)
    return {"messaged": messaged}
