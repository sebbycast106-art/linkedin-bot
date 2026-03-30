"""
Scraper for Handshake — university-specific job/co-op/internship listings.

Handshake (app.joinhandshake.com and northeastern.joinhandshake.com) requires
university SSO authentication for all job listing pages. Unauthenticated requests
are redirected to the login page (HTTP 200 with login HTML, or HTTP 403).
There is no public unauthenticated API endpoint.

This module is a graceful stub that:
  - Logs a clear message explaining why it cannot scrape without auth
  - Returns an empty list so the rest of the job scraper is unaffected
  - Accepts an optional Playwright `page` object in case future work adds
    authenticated scraping (the bot already holds a LinkedIn session, not
    a Handshake session, so that path is not wired up today)

If Handshake auth is added in the future, the authenticated approach would be:
  1. Log into app.joinhandshake.com via Playwright with university SSO
  2. Navigate to /jobs with filters: type=co-op, category=Finance
  3. Parse job cards from the DOM (selectors differ by institution)
  4. Store session cookies analogous to linkedin_cookies.json
"""
import datetime
from zoneinfo import ZoneInfo

HANDSHAKE_BASE = "https://app.joinhandshake.com"
NEU_HANDSHAKE = "https://northeastern.joinhandshake.com"


def scrape_handshake_jobs(seen_ids: set, page=None) -> list[dict]:
    """
    Attempt to scrape Handshake for finance/fintech co-op listings.

    Currently returns an empty list because Handshake requires university SSO
    authentication for all listing pages — unauthenticated requests are
    redirected to the login screen. No public API is available.

    Args:
        seen_ids: set of already-seen job_id strings (not used, kept for API parity)
        page: optional Playwright page object for authenticated scraping (not used)

    Returns:
        list[dict] — always empty until auth is implemented
    """
    print(
        "[handshake_scraper] skipping — Handshake requires university SSO login; "
        "no public API available. Returning 0 jobs.",
        flush=True,
    )
    return []


def _today_iso() -> str:
    return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()
