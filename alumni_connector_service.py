"""
alumni_connector_service.py — Search for Northeastern alumni at target finance/fintech firms
and send personalized connection requests referencing the shared school.

Daily limit: 10 connection requests/day (separate from main connector's 20/day).

Public interface:
    run_alumni_connections(session) -> dict
"""
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic

import config
import database
import profile_scraper
from linkedin_session import LinkedInSession, random_delay

_STATE_FILE = "alumni_connector_state.json"
_DAILY_CONNECT_LIMIT = 10

_TARGET_FIRMS = [
    "Citadel",
    "Jane Street",
    "Point72",
    "Two Sigma",
    "Bridgewater",
    "Goldman Sachs",
    "BlackRock",
    "Fidelity",
    "JPMorgan",
    "Morgan Stanley",
    "Sequoia",
    "General Catalyst",
    "Robinhood",
    "Stripe",
]


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _build_search_url(company: str) -> str:
    keywords = f"Northeastern University {company}"
    encoded = urllib.parse.quote_plus(keywords)
    return f"https://www.linkedin.com/search/results/people/?keywords={encoded}&network=%5B%22S%22%5D"


def _generate_alumni_message(name: str, company: str, headline: str = "", school: str = "") -> str:
    """Generate a personalized connection note for a NEU alum at a target firm.

    Calls Claude haiku (max_tokens=80). Falls back to a canned message on error.
    Result is always <= 300 chars.
    """
    fallback = (
        f"Hi {name}, fellow Northeastern student here! "
        f"Would love to connect and learn about your experience at {company}."
    )
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"Write a LinkedIn connection note (max 300 chars) from a Northeastern sophomore "
            f"to a NEU alum at {company}. Mention the shared Northeastern connection. "
            f"Their headline: {headline}. Be genuine and brief."
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        msg = response.content[0].text.strip().strip('"')
        if not msg:
            return fallback[:300]
        return msg[:300]
    except Exception as e:
        print(f"[alumni_connector] _generate_alumni_message error: {e}", flush=True)
        return fallback[:300]


def run_alumni_connections(session: LinkedInSession) -> dict:
    """Search for NEU alumni at target firms and send connection requests.

    Returns {"sent": N, "checked": M}.
    """
    default_state = {"date": _today(), "sent_today": 0, "connected_ids": []}
    state = database.load_state(_STATE_FILE, default=default_state)

    # Reset counter on new day
    if state.get("date") != _today():
        state = {"date": _today(), "sent_today": 0, "connected_ids": state.get("connected_ids", [])}

    connected_ids = set(state.get("connected_ids", []))
    total_sent = 0
    total_checked = 0

    page = session.new_page()
    profile_page = session.new_page()
    try:
        for company in _TARGET_FIRMS:
            if state.get("sent_today", 0) >= _DAILY_CONNECT_LIMIT:
                print("[alumni_connector] daily limit reached", flush=True)
                break

            url = _build_search_url(company)
            try:
                page.goto(url, timeout=20000)
                random_delay(3, 6)

                results = page.query_selector_all(".reusable-search__result-container")[:8]
                for result in results:
                    if state.get("sent_today", 0) >= _DAILY_CONNECT_LIMIT:
                        break
                    try:
                        name_el = result.query_selector(".entity-result__title-text a span[aria-hidden='true']")
                        link_el = result.query_selector("a.app-aware-link[href*='/in/']")

                        if not name_el or not link_el:
                            continue

                        name = name_el.inner_text().strip()
                        href = link_el.get_attribute("href") or ""
                        profile_id = (
                            href.split("/in/")[1].split("/")[0].split("?")[0]
                            if "/in/" in href
                            else ""
                        )

                        if not profile_id:
                            continue

                        total_checked += 1

                        if profile_id in connected_ids:
                            continue

                        enrichment = profile_scraper.scrape_profile(
                            profile_page,
                            f"https://www.linkedin.com/in/{profile_id}/",
                        )
                        headline = enrichment.get("headline", "")
                        school = enrichment.get("school", "")

                        connect_btn = result.query_selector(
                            "button[aria-label*='Connect'], button[aria-label*='Invite']"
                        )
                        if not connect_btn:
                            continue

                        connect_btn.click()
                        random_delay(1, 2)

                        add_note_btn = page.query_selector("button[aria-label='Add a note']")
                        if add_note_btn:
                            note = _generate_alumni_message(name, company, headline=headline, school=school)
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
                            random_delay(3, 6)
                            connected_ids.add(profile_id)
                            state["sent_today"] = state.get("sent_today", 0) + 1
                            state["connected_ids"] = list(connected_ids)[-2000:]
                            total_sent += 1
                            print(f"[alumni_connector] connected: {name} at {company}", flush=True)
                        else:
                            dismiss = page.query_selector("button[aria-label='Dismiss']")
                            if dismiss:
                                dismiss.click()

                        random_delay(3, 6)
                    except Exception as e:
                        print(f"[alumni_connector] person error: {e}", flush=True)

                random_delay(3, 6)
            except Exception as e:
                print(f"[alumni_connector] search error for {company}: {e}", flush=True)
    finally:
        page.close()
        profile_page.close()
        state["date"] = _today()
        database.save_state(_STATE_FILE, state)

    print(f"[alumni_connector] sent {total_sent} requests, checked {total_checked}", flush=True)
    return {"sent": total_sent, "checked": total_checked}
