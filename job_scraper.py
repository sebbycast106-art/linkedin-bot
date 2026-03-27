"""
job_scraper.py — Scrape LinkedIn Jobs for co-op/internship postings.

Public interface:
    scrape_new_jobs(session) -> list[dict]
    format_job_message(job: dict) -> str
    is_new_job(job_id: str, seen_ids: set) -> bool
    build_search_url(keywords: str, location: str) -> str
"""
import urllib.parse
import database

_STATE_FILE = "job_scraper_state.json"
_MAX_SEEN = 2000

_SEARCH_CONFIGS = [
    {"keywords": "co-op finance", "location": "United States"},
    {"keywords": "internship finance", "location": "Boston, MA"},
    {"keywords": "co-op business analyst", "location": "United States"},
    {"keywords": "internship investment banking", "location": "United States"},
    {"keywords": "co-op fintech", "location": "United States"},
]


def build_search_url(keywords: str, location: str) -> str:
    params = urllib.parse.urlencode({
        "keywords": keywords,
        "location": location,
        "f_JT": "I",
        "f_E": "1,2",
        "sortBy": "DD",
        "f_TPR": "r604800",
    })
    return f"https://www.linkedin.com/jobs/search/?{params}"


def format_job_message(job: dict) -> str:
    return (
        f"💼 {job['title']}\n"
        f"🏢 {job['company']}\n"
        f"📍 {job['location']}\n"
        f"🔗 {job['url']}"
    )


def is_new_job(job_id: str, seen_ids: set) -> bool:
    return job_id not in seen_ids


def _parse_jobs_from_page(page) -> list:
    jobs = []
    try:
        page.wait_for_selector(".jobs-search__results-list, .job-search-card", timeout=10000)
    except Exception:
        print("[job_scraper] no job results selector found", flush=True)
        return jobs

    cards = page.query_selector_all(".job-search-card, .jobs-search__results-list li")
    for card in cards[:15]:
        try:
            title_el = card.query_selector("h3.base-search-card__title, .job-search-card__title")
            company_el = card.query_selector("h4.base-search-card__subtitle, .job-search-card__subtitle")
            location_el = card.query_selector(".job-search-card__location, .base-search-card__metadata")
            link_el = card.query_selector("a.base-card__full-link, a[data-tracking-control-name]")

            if not title_el or not link_el:
                continue

            href = link_el.get_attribute("href") or ""
            job_id = href.split("/view/")[1].split("/")[0].split("?")[0] if "/view/" in href else href[-20:]

            jobs.append({
                "title": (title_el.inner_text() or "").strip(),
                "company": (company_el.inner_text() if company_el else "Unknown").strip(),
                "location": (location_el.inner_text() if location_el else "Unknown").strip(),
                "url": href.split("?")[0] if href else "",
                "job_id": job_id,
            })
        except Exception as e:
            print(f"[job_scraper] card parse error: {e}", flush=True)
    return jobs


def scrape_new_jobs(session) -> list:
    """Scrape all search configs, return only unseen jobs."""
    from linkedin_session import random_delay
    state = database.load_state(_STATE_FILE, default={"seen_ids": []})
    seen_list = state.get("seen_ids", [])
    seen_set = set(seen_list)

    new_jobs = []
    page = session.new_page()
    try:
        for cfg in _SEARCH_CONFIGS:
            url = build_search_url(cfg["keywords"], cfg["location"])
            try:
                page.goto(url, timeout=20000)
                random_delay(3, 5)
                jobs = _parse_jobs_from_page(page)
                for job in jobs:
                    if is_new_job(job["job_id"], seen_set):
                        new_jobs.append(job)
                        seen_list.append(job["job_id"])
                        seen_set.add(job["job_id"])
                random_delay(5, 10)
            except Exception as e:
                print(f"[job_scraper] search error '{cfg['keywords']}': {e}", flush=True)
    finally:
        page.close()

    state["seen_ids"] = seen_list[-_MAX_SEEN:]
    database.save_state(_STATE_FILE, state)
    print(f"[job_scraper] found {len(new_jobs)} new jobs", flush=True)
    return new_jobs
