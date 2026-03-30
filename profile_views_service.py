"""
profile_views_service.py — Connect with people who recently viewed your profile.

Daily limit: 10 connection requests/day
State file: profile_views_state.json

Public interface:
    run_profile_views_connect(session) -> dict  # {"sent": N, "checked": N}
"""
import database
import profile_scraper
import ai_service
from linkedin_session import random_delay
from datetime import datetime
from zoneinfo import ZoneInfo
from warmup_service import apply_limit

_STATE_FILE = "profile_views_state.json"
_DAILY_LIMIT = apply_limit(10)
_ANALYTICS_URL = "https://www.linkedin.com/analytics/profile-views/"

_VIEWER_SELECTORS = [
    ".profile-views-module__viewer-card",
    ".profile-views__viewer-card",
    ".pv-profile-view-card",
    ".artdeco-list__item",
]


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def run_profile_views_connect(session) -> dict:
    sent = 0
    checked = 0
    try:
        state = database.load_state(
            _STATE_FILE,
            default={"date": _today(), "sent_today": 0, "connected_viewer_ids": []},
        )

        # Reset daily counter if date has changed
        if state.get("date") != _today():
            state = {
                "date": _today(),
                "sent_today": 0,
                "connected_viewer_ids": state.get("connected_viewer_ids", []),
            }

        if state.get("sent_today", 0) >= _DAILY_LIMIT:
            print("[profile_views] daily limit already reached", flush=True)
            return {"sent": 0, "checked": 0}

        connected_viewer_ids = set(state.get("connected_viewer_ids", []))

        page = session.new_page()
        try:
            page.goto(_ANALYTICS_URL, timeout=20000)
            random_delay(3, 5)

            # Try each selector until we find viewer cards
            viewer_cards = []
            for selector in _VIEWER_SELECTORS:
                viewer_cards = page.query_selector_all(selector)
                if viewer_cards:
                    break

            for card in viewer_cards[:15]:
                if state.get("sent_today", 0) >= _DAILY_LIMIT:
                    break

                try:
                    # Extract profile link
                    link_el = card.query_selector("a[href*='/in/']")
                    if not link_el:
                        continue

                    href = link_el.get_attribute("href") or ""
                    profile_id = (
                        href.split("/in/")[1].split("/")[0].split("?")[0]
                        if "/in/" in href
                        else ""
                    )
                    if not profile_id:
                        continue

                    checked += 1

                    if profile_id in connected_viewer_ids:
                        continue

                    # Extract name
                    name_el = card.query_selector("span[aria-hidden='true']") or card.query_selector("h3")
                    name = name_el.inner_text().strip() if name_el else ""

                    try:
                        from warmth_scorer_service import record_signal
                        record_signal(profile_id, name, "viewed_profile")
                    except Exception:
                        pass

                    # Extract title
                    title_el = card.query_selector(".profile-views-module__viewer-card-subtitle") or \
                                card.query_selector(".artdeco-entity-lockup__subtitle") or \
                                card.query_selector(".entity-result__primary-subtitle")
                    title = title_el.inner_text().strip() if title_el else ""

                    # Scrape full profile for enrichment
                    profile_page = session.new_page()
                    try:
                        enrichment = profile_scraper.scrape_profile(
                            profile_page,
                            f"https://www.linkedin.com/in/{profile_id}/",
                        )
                    finally:
                        profile_page.close()

                    # Find Connect button within this viewer card.
                    # Also match "Invite" aria-label variant to be consistent with
                    # connector_service.py and avoid missing valid Connect buttons.
                    connect_btn = card.query_selector(
                        "button[aria-label*='Connect'], button[aria-label*='Invite']"
                    )
                    if not connect_btn:
                        continue

                    connect_btn.click()
                    random_delay(1, 2)

                    # Handle "Add a note" modal
                    add_note_btn = page.query_selector("button[aria-label='Add a note']")
                    if add_note_btn:
                        company = enrichment.get("company", "")
                        if not company and " at " in title:
                            company = title.split(" at ")[-1]
                        role = title.split(" at ")[0] if " at " in title else title

                        note = ai_service.generate_connection_message(
                            name,
                            role,
                            company,
                            school=enrichment.get("school", ""),
                            headline=enrichment.get("headline", ""),
                        )
                        if note:
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
                        connected_viewer_ids.add(profile_id)
                        state["sent_today"] = state.get("sent_today", 0) + 1
                        # Cap at 2000 entries to prevent unbounded growth (matches other services)
                        state["connected_viewer_ids"] = list(connected_viewer_ids)[-2000:]
                        sent += 1
                        print(f"[profile_views] connected: {name}", flush=True)
                    else:
                        dismiss = page.query_selector("button[aria-label='Dismiss']")
                        if dismiss:
                            dismiss.click()

                    random_delay(5, 10)

                except Exception as e:
                    print(f"[profile_views] card error: {e}", flush=True)

        finally:
            page.close()
            state["date"] = _today()
            state["connected_viewer_ids"] = list(connected_viewer_ids)[-2000:]
            database.save_state(_STATE_FILE, state)

        print(f"[profile_views] checked={checked} sent={sent}", flush=True)
        return {"sent": sent, "checked": checked}

    except Exception:
        raise
