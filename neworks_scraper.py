"""
neworks_scraper.py — Scrape co-op job listings from NUWorks (jobs.northeastern.edu).

NEU SSO login via Playwright with trusted-device Duo 2FA handling.
Cookies are saved to neworks_cookies.json and reused on subsequent runs.
If Duo push approval is required, a Telegram alert is sent and the run aborts.

State files:
    neworks_cookies.json  — Playwright cookie list (separate from state, like linkedin_cookies.json)
    neworks_state.json    — {"seen_ids": [...last 2000...]}

Public interface:
    load_neworks_cookies() -> list
    save_neworks_cookies(cookies: list) -> None
    is_authenticated(page) -> bool
    perform_sso_login(page, context) -> bool
    scrape_neworks_jobs(page, seen_ids: set) -> list[dict]
    run_neworks_scraper() -> dict
    run_neworks_login() -> dict
"""
import time
import random

import database
import config

_COOKIES_FILE = "neworks_cookies.json"
_STATE_FILE = "neworks_state.json"
_MAX_SEEN = 2000
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# NUWorks / NEU SSO URLs
_NEWORKS_BASE = "https://neworks.northeastern.edu"
_NEWORKS_JOBS_URL = (
    "https://neworks.northeastern.edu/app/jobs#"
    "?page=1&pageSize=25&sortBy=postDate&ascending=false"
    "&position.positionTypes=Co-op"
)
_NEU_SSO_HOST = "northeastern.edu"
_DUO_PUSH_PHRASES = [
    "pushed a login request",
    "a login request was sent",
    "check your device",
    "approve it in the duo mobile app",
]


def _random_delay(min_s: float = 1.5, max_s: float = 3.5):
    time.sleep(random.uniform(min_s, max_s))


def _make_browser(pw):
    """Create a Playwright browser with anti-detection settings (mirrors LinkedInSession)."""
    return pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--no-zygote",
            "--single-process",
        ],
    )


def _make_context(browser):
    """Create a browser context matching LinkedInSession settings."""
    ctx = browser.new_context(
        user_agent=_USER_AGENT,
        viewport={"width": 1366, "height": 768},
        locale="en-US",
    )
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return ctx


# ── Cookie helpers ────────────────────────────────────────────────────────────

def load_neworks_cookies() -> list:
    """Load saved NUWorks cookies. Returns [] if file missing or empty."""
    return database.load_state(_COOKIES_FILE, default=[])


def save_neworks_cookies(cookies: list) -> None:
    """Persist Playwright cookie list to neworks_cookies.json."""
    database.save_state(_COOKIES_FILE, cookies)


# ── Authentication ────────────────────────────────────────────────────────────

def is_authenticated(page) -> bool:
    """
    Navigate to NUWorks and check for a logged-in indicator.
    Returns True if authenticated, False otherwise.
    Does NOT raise.
    """
    try:
        page.goto(_NEWORKS_BASE, timeout=20000)
        _random_delay(2, 3)
        url = page.url.lower()
        # If we end up on the NEU SSO login page, we're not authenticated
        if "myapps.microsoft.com" in url or "login.microsoftonline" in url:
            return False
        if "login" in url and _NEU_SSO_HOST in url:
            return False
        # Check for a known authenticated element or URL pattern
        # NUWorks dashboard shows the app root without redirecting to SSO
        if "neworks.northeastern.edu" in url:
            # Try to detect the logged-in nav/dashboard indicator
            for sel in ["[data-role='student']", ".student-nav", "#app", "nw-app"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        return True
                except Exception:
                    pass
            # Fallback: if page loaded without redirecting to SSO, assume logged in
            if "login" not in url and "sso" not in url:
                return True
        return False
    except Exception as e:
        print(f"[neworks] is_authenticated error: {e}", flush=True)
        return False


def perform_sso_login(page, context) -> bool:
    """
    Execute NEU SSO login via Microsoft / Shibboleth.

    Flow:
      1. Navigate to NUWorks login trigger
      2. Fill username + password on NEU SSO page
      3. Submit and wait for redirect
      4. Detect Duo state:
         - Auto-approved (trusted device): redirect to NUWorks -> True
         - "Pushed a login request": Duo push sent -> return False
         - Stayed on login page: credentials bad -> raise
      5. On success: save cookies

    Returns True on success, False if Duo push approval needed.
    """
    try:
        username = config.NORTHEASTERN_USERNAME()
        password = config.NORTHEASTERN_PASSWORD()
    except RuntimeError as e:
        raise RuntimeError(f"NEU credentials not set: {e}") from e

    try:
        # Navigate to NUWorks — it will redirect to NEU SSO
        page.goto(_NEWORKS_BASE + "/app/login", timeout=20000)
        _random_delay(2, 3)

        # Fill credentials — NEU SSO uses Microsoft / standard HTML form
        # Try multiple selector patterns used by NEU's SSO
        for sel in ["input[name='loginfmt']", "input[type='email']", "#i0116", "input[name='username']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    page.fill(sel, username)
                    _random_delay(0.5, 1.0)
                    # Click "Next" / submit username step
                    for btn in ["input[type='submit']", "button[type='submit']", "#idSIButton9"]:
                        try:
                            page.click(btn, timeout=3000)
                            break
                        except Exception:
                            pass
                    _random_delay(1.5, 2.5)
                    break
            except Exception:
                pass

        # Fill password
        for sel in ["input[name='passwd']", "input[type='password']", "#i0118", "input[name='password']"]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    page.fill(sel, password)
                    _random_delay(0.5, 1.0)
                    for btn in ["input[type='submit']", "button[type='submit']", "#idSIButton9"]:
                        try:
                            page.click(btn, timeout=3000)
                            break
                        except Exception:
                            pass
                    _random_delay(2, 3)
                    break
            except Exception:
                pass

        # Wait for redirect (SSO → NUWorks or Duo)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        _random_delay(2, 3)

        current_url = page.url.lower()
        page_text = ""
        try:
            page_text = (page.inner_text("body") or "").lower()
        except Exception:
            pass

        # Check for Duo push state
        for phrase in _DUO_PUSH_PHRASES:
            if phrase in page_text:
                print(f"[neworks] Duo push sent — waiting for approval", flush=True)
                return False

        # If Duo iframe is present but no push phrase found, it may need a click
        if "duosecurity" in current_url or "duo" in page_text[:200]:
            # Try clicking "Send Me a Push"
            for sel in ["button:has-text('Send Me a Push')", "#push-button", "[name='dampen_choice']"]:
                try:
                    page.click(sel, timeout=3000)
                    _random_delay(2, 3)
                    page_text = (page.inner_text("body") or "").lower()
                    for phrase in _DUO_PUSH_PHRASES:
                        if phrase in page_text:
                            return False
                    break
                except Exception:
                    pass

        # Check if we're back on NUWorks (success)
        if "neworks.northeastern.edu" in current_url and "login" not in current_url:
            cookies = context.cookies()
            save_neworks_cookies(cookies)
            print(f"[neworks] SSO login successful, saved {len(cookies)} cookies", flush=True)
            return True

        # If still on SSO/login page, credentials may be wrong
        if "login" in current_url or _NEU_SSO_HOST in current_url:
            raise RuntimeError(
                f"NEU SSO login failed — still on login page: {page.url}"
            )

        # Unexpected state — save cookies optimistically and return True
        cookies = context.cookies()
        save_neworks_cookies(cookies)
        print(f"[neworks] SSO login: unexpected URL {page.url}, proceeding", flush=True)
        return True

    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"NEU SSO login error: {e}") from e


# ── Scraping ──────────────────────────────────────────────────────────────────

def scrape_neworks_jobs(page, seen_ids: set) -> list:
    """
    Navigate NUWorks co-op job listings and extract unseen jobs.

    NOTE: NUWorks is a modern SPA (Angular). The actual DOM structure is confirmed
    by inspecting jobs.northeastern.edu after authentication. If selectors break,
    update _NEWORKS_JOBS_URL and the selectors below to match the live DOM.

    Returns list of dicts: {job_id, title, company, location, url, description}
    """
    new_jobs = []

    try:
        page.goto(_NEWORKS_JOBS_URL, timeout=30000)
        _random_delay(3, 5)  # SPA needs time to render

        # Wait for job cards to appear
        try:
            page.wait_for_selector(
                "a[href*='/app/jobs/'], .job-listing, nw-job-list-item, [class*='job-card']",
                timeout=15000,
            )
        except Exception:
            print("[neworks] no job card selector found — SPA may still be loading", flush=True)
            _random_delay(3, 5)

        # Try to extract job cards
        # NUWorks SPA uses Angular components; common selectors for NUWorks:
        cards = []
        for sel in [
            "nw-job-list-item",
            ".job-listing-item",
            "[data-cy='job-card']",
            "a[href*='/app/jobs/']",
        ]:
            try:
                found = page.query_selector_all(sel)
                if found:
                    cards = found
                    print(f"[neworks] found {len(found)} cards with selector: {sel}", flush=True)
                    break
            except Exception:
                pass

        if not cards:
            # Fallback: log page source snippet to help debug selectors
            try:
                body_text = page.inner_text("body")[:500]
                print(f"[neworks] no cards found. Page preview: {body_text!r}", flush=True)
            except Exception:
                pass
            return new_jobs

        for card in cards:
            try:
                job_id = None
                url = ""

                # Extract URL / job_id
                try:
                    href = card.get_attribute("href") or ""
                    if not href:
                        link = card.query_selector("a[href*='/app/jobs/']")
                        href = link.get_attribute("href") if link else ""
                    if href:
                        url = href if href.startswith("http") else _NEWORKS_BASE + href
                        # Extract ID from URL like /app/jobs/12345 or /app/jobs?id=12345
                        import re
                        m = re.search(r"/jobs/(\d+)", href)
                        if m:
                            job_id = m.group(1)
                        else:
                            m = re.search(r"[?&]id=(\d+)", href)
                            if m:
                                job_id = m.group(1)
                except Exception:
                    pass

                if not job_id:
                    continue

                full_job_id = f"neworks_{job_id}"
                if full_job_id in seen_ids:
                    continue
                # Use full_job_id for the rest of processing
                job_id = full_job_id

                # Extract text fields
                title = ""
                company = ""
                location = ""

                for sel in [".job-title", "[class*='title']", "h3", "h4", "[data-cy='job-title']"]:
                    try:
                        el = card.query_selector(sel)
                        if el:
                            title = (el.inner_text() or "").strip()
                            if title:
                                break
                    except Exception:
                        pass

                for sel in [".employer-name", "[class*='employer']", "[class*='company']", "[data-cy='employer']"]:
                    try:
                        el = card.query_selector(sel)
                        if el:
                            company = (el.inner_text() or "").strip()
                            if company:
                                break
                    except Exception:
                        pass

                for sel in [".job-location", "[class*='location']", "[data-cy='location']"]:
                    try:
                        el = card.query_selector(sel)
                        if el:
                            location = (el.inner_text() or "").strip()
                            if location:
                                break
                    except Exception:
                        pass

                if not title:
                    # Try card's full text as fallback title
                    try:
                        full_text = (card.inner_text() or "").strip()
                        title = full_text[:80] if full_text else f"NUWorks Job {job_id}"
                    except Exception:
                        title = f"NUWorks Job {job_id}"

                new_jobs.append({
                    "job_id": job_id,  # already "neworks_{raw_id}" from above
                    "title": title,
                    "company": company or "Unknown",
                    "location": location,
                    "url": url,
                    "source": "neworks",
                    "description": "",
                })

            except Exception as e:
                print(f"[neworks] error parsing card: {e}", flush=True)
                continue

    except Exception as e:
        print(f"[neworks] scrape error: {e}", flush=True)

    return new_jobs


# ── Entry points ──────────────────────────────────────────────────────────────

def run_neworks_scraper() -> dict:
    """
    Main scraper entry point. Called from app.py background thread.

    1. Create browser, inject saved cookies
    2. Check authentication
    3. If not authenticated: run SSO login
       - Duo push needed → Telegram alert → return {status: "duo_required"}
       - Login error → return {status: "auth_failed", error: ...}
    4. Scrape job listings
    5. Score with filter_and_score_jobs(min_score=6)
    6. Add to application_tracker with source="neworks", status="seen"
    7. Send Telegram summary
    8. Persist updated seen_ids

    Returns: {"status": "ok"|"duo_required"|"auth_failed", "scraped": N, "new": M, "relevant": K}
    """
    from playwright.sync_api import sync_playwright
    from job_scorer import filter_and_score_jobs
    from application_tracker import add_application
    from telegram_service import send_telegram, block

    state = database.load_state(_STATE_FILE, default={"seen_ids": []})
    seen_list: list = state.get("seen_ids", [])
    seen_set: set = set(seen_list)

    pw = sync_playwright().start()
    browser = None
    try:
        browser = _make_browser(pw)
        context = _make_context(browser)

        # Inject saved cookies
        cookies = load_neworks_cookies()
        if cookies:
            try:
                context.add_cookies(cookies)
            except Exception as e:
                print(f"[neworks] cookie inject error: {e}", flush=True)

        page = context.new_page()

        # Check authentication
        authenticated = is_authenticated(page)
        if not authenticated:
            print("[neworks] not authenticated — attempting SSO login", flush=True)
            try:
                success = perform_sso_login(page, context)
            except RuntimeError as e:
                send_telegram(block("NEWORKS [auth failed]", [("reason", str(e)[:80])]))
                return {"status": "auth_failed", "error": str(e)}

            if not success:
                send_telegram(
                    "🔐 <b>NUWorks login requires Duo approval on your phone.</b>\n\n"
                    "Approve the push, then trigger <b>NUWorks Login</b> from Controls to save session."
                )
                return {"status": "duo_required", "scraped": 0, "new": 0, "relevant": 0}

        # Scrape
        new_jobs = scrape_neworks_jobs(page, seen_set)
        scraped_count = len(new_jobs)
        print(f"[neworks] scraped {scraped_count} new jobs", flush=True)

        # Save cookies after successful session
        try:
            fresh_cookies = context.cookies()
            if fresh_cookies:
                save_neworks_cookies(fresh_cookies)
        except Exception:
            pass

        page.close()

        if not new_jobs:
            print("[neworks] no new jobs found", flush=True)
            return {"status": "ok", "scraped": 0, "new": 0, "relevant": 0}

        # Score
        scored_jobs = filter_and_score_jobs(new_jobs, min_score=6)
        print(f"[neworks] {len(scored_jobs)} jobs scored ≥6", flush=True)

        # Track all new jobs, add score for relevant ones
        relevant_count = 0
        for job in new_jobs:
            scored = next((s for s in scored_jobs if s["job_id"] == job["job_id"]), None)
            score = scored.get("score") if scored else None
            try:
                add_application(
                    job["job_id"],
                    job["company"],
                    job["title"],
                    job.get("url", ""),
                    status="seen",
                    source="neworks",
                    score=score,
                )
                if scored:
                    relevant_count += 1
            except Exception as e:
                print(f"[neworks] add_application error: {e}", flush=True)

        # Telegram summary
        lines = [
            ("scraped", scraped_count),
            ("relevant", f"{relevant_count}  (score ≥6)"),
        ]
        send_telegram(block("NEWORKS", lines))

        if scored_jobs:
            job_lines = []
            for j in scored_jobs[:5]:
                score_str = f"  [{j.get('score', '?')}/10]" if j.get("score") else ""
                job_lines.append(
                    f"🎓 <b>{j['company']}</b>: {j['title']}{score_str}\n"
                    f"<a href='{j.get('url', '')}'>View on NUWorks</a>"
                )
            send_telegram("\n\n".join(job_lines), parse_mode="HTML")

        # Persist updated seen_ids
        for job in new_jobs:
            seen_list.append(job["job_id"])
        state["seen_ids"] = seen_list[-_MAX_SEEN:]
        database.save_state(_STATE_FILE, state)

        return {
            "status": "ok",
            "scraped": scraped_count,
            "new": scraped_count,
            "relevant": relevant_count,
        }

    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass


def run_neworks_login() -> dict:
    """
    Forced re-auth entry point for /internal/neworks-login endpoint.
    Clears existing cookies, then runs perform_sso_login.
    Used after Duo push approval or when cookies expire.

    Returns: {"status": "ok"} | {"status": "duo_required"} | {"status": "failed", "error": ...}
    """
    from playwright.sync_api import sync_playwright
    from telegram_service import send_telegram

    # Clear old cookies
    save_neworks_cookies([])
    print("[neworks] cleared cookies for fresh login", flush=True)

    pw = sync_playwright().start()
    browser = None
    try:
        browser = _make_browser(pw)
        context = _make_context(browser)
        page = context.new_page()

        try:
            success = perform_sso_login(page, context)
        except RuntimeError as e:
            send_telegram(f"❌ NUWorks login failed: {str(e)[:100]}")
            return {"status": "failed", "error": str(e)}

        if not success:
            send_telegram(
                "🔐 <b>NUWorks Duo push sent.</b>\n\n"
                "Approve it on your phone, then trigger <b>NUWorks Login</b> again."
            )
            return {"status": "duo_required"}

        send_telegram("✅ NUWorks login successful — cookies saved for ~30 days.")
        return {"status": "ok"}

    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass
