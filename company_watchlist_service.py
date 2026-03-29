"""
company_watchlist_service.py — Alert when target companies post new co-op/internship listings.

Checks daily for new job postings from a watchlist of target companies.
State file: watchlist_state.json — tracks seen job IDs per company.

Public interface:
    run_watchlist_check(session) -> dict  # {"alerts_sent": N, "companies_checked": N}
"""
import urllib.parse
import database
from linkedin_session import random_delay
from telegram_service import send_telegram

_STATE_FILE = "watchlist_state.json"
_MAX_SEEN = 5000

_WATCHLIST = [
    {"company": "Citadel", "keywords": "co-op intern Citadel"},
    {"company": "Jane Street", "keywords": "co-op intern Jane Street"},
    {"company": "Point72", "keywords": "co-op intern Point72"},
    {"company": "Fidelity", "keywords": "co-op intern Fidelity"},
    {"company": "BlackRock", "keywords": "co-op intern BlackRock"},
    {"company": "Goldman Sachs", "keywords": "co-op intern Goldman Sachs"},
    {"company": "Two Sigma", "keywords": "co-op intern Two Sigma"},
    {"company": "Bridgewater", "keywords": "co-op intern Bridgewater"},
    {"company": "Stripe", "keywords": "co-op intern Stripe"},
    {"company": "Robinhood", "keywords": "co-op intern Robinhood"},
]


def run_watchlist_check(session) -> dict:
    """Check each target company for new co-op/internship listings and alert via Telegram."""
    state = database.load_state(_STATE_FILE, default={"seen_ids": []})
    seen_ids = state.get("seen_ids", [])
    seen_set = set(seen_ids)

    alerts_sent = 0
    companies_checked = 0

    page = session.new_page()
    try:
        for entry in _WATCHLIST:
            company = entry["company"]
            try:
                params = urllib.parse.urlencode({
                    "keywords": entry["keywords"],
                    "location": "United States",
                    "f_JT": "I",
                    "f_E": "1,2",
                    "sortBy": "DD",
                    "f_TPR": "r86400",
                })
                url = f"https://www.linkedin.com/jobs/search/?{params}"

                page.goto(url, timeout=20000)
                random_delay(3, 5)

                try:
                    page.wait_for_selector(
                        ".jobs-search__results-list, .job-search-card",
                        timeout=8000,
                    )
                except Exception:
                    print(f"[watchlist] no results selector found for {company}", flush=True)

                cards = page.query_selector_all(
                    ".job-search-card, .jobs-search__results-list li"
                )[:5]

                for card in cards:
                    try:
                        title_el = card.query_selector(
                            "h3.base-search-card__title, .job-search-card__title"
                        )
                        link_el = card.query_selector("a.base-card__full-link")
                        location_el = card.query_selector(".job-search-card__location")

                        if not title_el or not link_el:
                            continue

                        href = link_el.get_attribute("href") or ""
                        job_id = (
                            href.split("/view/")[1].split("/")[0].split("?")[0]
                            if "/view/" in href
                            else href[-20:]
                        )

                        if job_id in seen_set:
                            continue

                        title = (title_el.inner_text() or "").strip()
                        location = (
                            location_el.inner_text() if location_el else "Unknown"
                        ).strip()
                        job_url = href.split("?")[0] if href else href

                        message = (
                            f"🚨 New {company} listing:\n"
                            f"💼 {title}\n"
                            f"📍 {location}\n"
                            f"🔗 {job_url}"
                        )
                        send_telegram(message)

                        seen_ids.append(job_id)
                        seen_set.add(job_id)
                        alerts_sent += 1

                    except Exception as e:
                        print(f"[watchlist] card parse error for {company}: {e}", flush=True)

                random_delay(5, 8)
                companies_checked += 1

            except Exception as e:
                print(f"[watchlist] error processing {company}: {e}", flush=True)

    except Exception:
        raise
    finally:
        page.close()

    state["seen_ids"] = seen_ids[-_MAX_SEEN:]
    database.save_state(_STATE_FILE, state)
    print(
        f"[watchlist] checked {companies_checked} companies, sent {alerts_sent} alerts",
        flush=True,
    )
    return {"alerts_sent": alerts_sent, "companies_checked": companies_checked}
