"""
Scraper for Simplify.jobs — curated verified internship/co-op listings.

Uses the SimplifyJobs public GitHub repo (SimplifyJobs/Summer2025-Internships)
which contains structured JSON data for all listings Simplify tracks.
The site itself has no public REST API (all endpoints return 404 or HTML),
so the GitHub-hosted JSON is the canonical public data source.

Data URL:
  https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships/dev/.github/scripts/listings.json

Schema per item:
  id, title, company_name, url, locations (list), terms (list),
  active (bool), category, date_posted (unix ts), sponsorship
"""
import requests
import datetime
from zoneinfo import ZoneInfo

_LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2025-Internships"
    "/dev/.github/scripts/listings.json"
)

# Categories that map to finance/fintech/quant roles
_TARGET_CATEGORIES = {
    "Quantitative Finance",
    "Quant",
    "Data Science, AI & Machine Learning",
    "AI/ML/Data",
    "Product Management",
    "Product",
    "Other",  # broad — filtered further by keyword
}

# Finance-adjacent keywords to catch relevant "Other" / "Software" listings
_FINANCE_KEYWORDS = {
    "finance",
    "fintech",
    "financial",
    "investment",
    "banking",
    "trading",
    "quant",
    "quantitative",
    "asset management",
    "hedge fund",
    "capital",
    "equity",
    "credit",
    "risk",
    "portfolio",
    "revenue",
    "payment",
}

# Target firms the user is interested in (CLAUDE.md)
_TARGET_COMPANIES = {
    "citadel",
    "jane street",
    "point72",
    "two sigma",
    "goldman sachs",
    "blackrock",
    "fidelity",
    "jpmorgan",
    "morgan stanley",
    "robinhood",
    "stripe",
    "sequoia",
    "general catalyst",
    "capital one",
    "wells fargo",
    "bank of america",
    "barclays",
    "ubs",
    "deutsche bank",
    "citi",
    "citibank",
    "bloomberg",
    "deloitte",
    "pwc",
    "kpmg",
    "ey",
    "ernst",
}


def _today_iso() -> str:
    return datetime.datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _is_relevant(item: dict) -> bool:
    """Return True if this listing is relevant to finance/fintech."""
    category = (item.get("category") or "").strip()
    title = (item.get("title") or "").lower()
    company = (item.get("company_name") or "").lower()

    # Always include quant/finance categories
    if category in ("Quantitative Finance", "Quant"):
        return True

    # Include if any finance keyword appears in title
    if any(kw in title for kw in _FINANCE_KEYWORDS):
        return True

    # Include if company is a known target firm
    if any(tc in company for tc in _TARGET_COMPANIES):
        return True

    return False


def scrape_simplify_jobs(seen_ids: set) -> list[dict]:
    """
    Fetch active internship/co-op listings from the SimplifyJobs GitHub repo.
    Returns a list of job dicts compatible with job_scraper.py format:
      {job_id, title, company, location, url, source, posted_date}

    Filters for finance/fintech/quant relevance before returning.
    Silently returns [] on any error so LinkedIn scraping is never blocked.
    """
    try:
        resp = requests.get(
            _LISTINGS_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
            timeout=20,
        )
        if resp.status_code != 200:
            print(
                f"[simplify_scraper] GitHub fetch failed: HTTP {resp.status_code}",
                flush=True,
            )
            return []

        data = resp.json()
    except Exception as e:
        print(f"[simplify_scraper] fetch error: {e}", flush=True)
        return []

    jobs = []
    seen_in_run: set[str] = set()

    for item in data:
        try:
            # Only active listings
            if not item.get("active"):
                continue

            # Only relevant-to-finance roles
            if not _is_relevant(item):
                continue

            raw_id = item.get("id") or ""
            job_id = f"simplify_{raw_id}"
            if not raw_id or job_id in seen_ids or job_id in seen_in_run:
                continue
            seen_in_run.add(job_id)

            # Locations: list → join first two, fall back to "Remote"
            locations = item.get("locations") or []
            if locations:
                location = ", ".join(locations[:2])
                if len(locations) > 2:
                    location += f" +{len(locations) - 2} more"
            else:
                location = "Remote / Multiple"

            # date_posted is a unix timestamp
            raw_ts = item.get("date_posted")
            if raw_ts:
                try:
                    posted_date = datetime.datetime.fromtimestamp(
                        raw_ts, tz=ZoneInfo("America/New_York")
                    ).date().isoformat()
                except Exception:
                    posted_date = _today_iso()
            else:
                posted_date = _today_iso()

            jobs.append(
                {
                    "job_id": job_id,
                    "title": (item.get("title") or "").strip(),
                    "company": (item.get("company_name") or "").strip(),
                    "location": location,
                    "url": (item.get("url") or "").strip(),
                    "source": "simplify",
                    "posted_date": posted_date,
                }
            )
        except Exception as e:
            print(f"[simplify_scraper] item parse error: {e}", flush=True)
            continue

    print(f"[simplify_scraper] {len(jobs)} relevant active listings found", flush=True)
    return jobs
