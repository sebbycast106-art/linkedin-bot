"""
connector_service.py — Find and connect with targeted LinkedIn profiles.

Daily limit: 20 connection requests/day.

Targets: Northeastern alumni, finance professionals, startup founders, VCs.

Public interface:
    run_daily_connections(session) -> int
"""
import urllib.parse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from linkedin_session import LinkedInSession, random_delay
import ai_service
import database
import profile_scraper
from warmup_service import apply_limit

_STATE_FILE = "connector_state.json"
_BASE_CONNECT_LIMIT = 20

_SEARCH_QUERIES = [
    {"keywords": "finance Northeastern University", "network": "S,O"},
    {"keywords": "investment banking analyst Boston", "network": "O"},
    {"keywords": "venture capital associate Boston", "network": "O"},
    {"keywords": "fintech startup founder", "network": "O"},
    {"keywords": "DMSB Northeastern co-op", "network": "S,O"},
]


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _this_monday() -> str:
    today = datetime.now(ZoneInfo("America/New_York")).date()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def _get_daily_count(state: dict) -> int:
    if state.get("date") != _today():
        return 0
    return state.get("connects_today", 0)


def _increment(state: dict) -> dict:
    today = _today()
    monday = _this_monday()
    if state.get("date") != today:
        state = {**state, "date": today, "connects_today": 0, "connected_ids": state.get("connected_ids", [])}
    state["connects_today"] = state.get("connects_today", 0) + 1
    # Weekly tracking
    if state.get("week_start") != monday:
        state["sent_this_week"] = 0
        state["week_start"] = monday
    state["sent_this_week"] = state.get("sent_this_week", 0) + 1
    # Response rate tracking
    state["total_sent"] = state.get("total_sent", 0) + 1
    daily_stats = state.get("daily_stats", [])
    if daily_stats and daily_stats[-1].get("date") == today:
        daily_stats[-1]["sent"] = daily_stats[-1].get("sent", 0) + 1
    else:
        daily_stats.append({"date": today, "sent": 1, "accepted": 0})
    state["daily_stats"] = daily_stats[-90:]  # keep last 90 days
    return state


def _build_search_url(keywords: str, network: str = "O") -> str:
    params = urllib.parse.urlencode({"keywords": keywords, "network": network})
    return f"https://www.linkedin.com/search/results/people/?{params}"


def run_daily_connections(session: LinkedInSession) -> int:
    state = database.load_state(_STATE_FILE, default={"date": _today(), "connects_today": 0, "connected_ids": [], "week_start": _this_monday(), "sent_this_week": 0})
    # Ensure weekly tracking fields exist and are current
    if state.get("week_start") != _this_monday():
        state["sent_this_week"] = 0
        state["week_start"] = _this_monday()
    connected_ids = set(state.get("connected_ids", []))
    total_sent = 0

    page = session.new_page()
    profile_page = session.new_page()
    try:
        for query in _SEARCH_QUERIES:
            if _get_daily_count(state) >= apply_limit(_BASE_CONNECT_LIMIT):
                print("[connector] daily limit reached", flush=True)
                break

            url = _build_search_url(query["keywords"], query.get("network", "O"))
            try:
                page.goto(url, timeout=20000)
                random_delay(3, 5)

                results = page.query_selector_all(".reusable-search__result-container")[:8]
                for result in results:
                    if _get_daily_count(state) >= apply_limit(_BASE_CONNECT_LIMIT):
                        break
                    try:
                        name_el = result.query_selector(".entity-result__title-text a span[aria-hidden='true']")
                        title_el = result.query_selector(".entity-result__primary-subtitle")
                        link_el = result.query_selector("a.app-aware-link[href*='/in/']")

                        if not name_el or not link_el:
                            continue

                        name = name_el.inner_text().strip()
                        title = (title_el.inner_text() if title_el else "").strip()
                        href = link_el.get_attribute("href") or ""
                        profile_id = href.split("/in/")[1].split("/")[0].split("?")[0] if "/in/" in href else ""

                        if not profile_id or profile_id in connected_ids:
                            continue

                        enrichment = profile_scraper.scrape_profile(profile_page, f"https://www.linkedin.com/in/{profile_id}/")
                        school = enrichment.get("school", "")
                        headline = enrichment.get("headline", "")

                        connect_btn = result.query_selector("button[aria-label*='Connect'], button[aria-label*='Invite']")
                        if not connect_btn:
                            continue

                        connect_btn.click()
                        random_delay(1, 2)

                        add_note_btn = page.query_selector("button[aria-label='Add a note']")
                        if add_note_btn:
                            company = title.split(" at ")[-1] if " at " in title else ""
                            role = title.split(" at ")[0] if " at " in title else title
                            note = ai_service.generate_connection_message(name, role, company, school=school, headline=headline)
                            if note:
                                add_note_btn.click()
                                random_delay(0.5, 1)
                                note_box = page.query_selector("textarea#custom-message")
                                if note_box:
                                    note_box.fill(note)
                                    random_delay(0.5, 1)

                        send_btn = page.query_selector("button[aria-label='Send now'], button[aria-label='Send invitation']")
                        if send_btn:
                            send_btn.click()
                            random_delay(2, 4)
                            connected_ids.add(profile_id)
                            state = _increment(state)
                            state["connected_ids"] = list(connected_ids)[-2000:]
                            total_sent += 1
                            print(f"[connector] connected: {name}", flush=True)
                        else:
                            dismiss = page.query_selector("button[aria-label='Dismiss']")
                            if dismiss:
                                dismiss.click()

                        random_delay(8, 15)
                    except Exception as e:
                        print(f"[connector] person error: {e}", flush=True)

                random_delay(10, 20)
            except Exception as e:
                print(f"[connector] search error: {e}", flush=True)
    finally:
        page.close()
        profile_page.close()
        database.save_state(_STATE_FILE, state)

    print(f"[connector] sent {total_sent} requests", flush=True)
    return total_sent


def get_response_rate() -> dict:
    """Return connection request acceptance rate stats."""
    state = database.load_state(_STATE_FILE, {})
    total_sent = state.get("total_sent", 0)
    total_accepted = state.get("total_accepted", 0)
    rate = round(total_accepted / total_sent * 100, 1) if total_sent > 0 else 0.0
    return {
        "total_sent": total_sent,
        "total_accepted": total_accepted,
        "accept_rate_pct": rate,
        "daily_stats": state.get("daily_stats", [])[-30:],  # last 30 days
    }
