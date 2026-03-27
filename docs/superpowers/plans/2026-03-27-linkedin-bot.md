# LinkedIn Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a headless LinkedIn bot that scrapes co-op/internship jobs, auto-comments on targeted hashtag posts using AI-generated responses, and auto-connects with targeted people — all triggered via Flask endpoints on a cron schedule.

**Architecture:** Playwright (headless Chromium) handles all LinkedIn browser automation with anti-detection stealth settings. A Flask app exposes `/internal/*` endpoints gated by `SCHEDULER_SECRET`. All slow operations run in background threads to avoid Railway's 30s edge timeout. State (cookies, dedup IDs, daily action counts) persists in JSON files via a simple database module.

**Tech Stack:** Python 3.11, Flask, Playwright (sync), playwright-stealth, Anthropic Claude API, Telegram Bot API, Railway (Docker), cron-job.org

---

## File Structure

```
linkedin-bot/
├── Dockerfile                  # Playwright-ready Docker image for Railway
├── Procfile                    # gunicorn command
├── requirements.txt            # All dependencies pinned
├── .gitignore
├── .env.example                # Required env vars documented
├── config.py                   # Lambda accessors for env vars
├── database.py                 # load_json / save_json with atomic writes
├── telegram_service.py         # send_telegram(msg) wrapper
├── linkedin_session.py         # Playwright session: login, cookies, stealth, delays
├── job_scraper.py              # Scrape LinkedIn Jobs for co-ops, dedup, format
├── ai_service.py               # Claude API: generate contextual comments
├── engagement_service.py       # Like posts, comment on posts, daily action limits
├── connector_service.py        # Find people by criteria, send connection requests
├── app.py                      # Flask app with /internal/* endpoints
└── tests/
    ├── conftest.py
    ├── test_job_scraper.py
    ├── test_ai_service.py
    └── test_engagement_service.py
```

---

### Task 1: Project Scaffold

**Files:**
- Create: `Dockerfile`
- Create: `Procfile`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.py`
- Create: `database.py`
- Create: `telegram_service.py`

- [ ] **Step 1: Create `requirements.txt`**

```
flask==3.0.3
gunicorn==22.0.0
playwright==1.44.0
playwright-stealth==1.0.6
anthropic==0.28.0
python-dotenv==1.0.1
requests==2.32.3
pytest==8.3.2
pytest-mock==3.14.0
```

- [ ] **Step 2: Create `Dockerfile`**

The official Playwright image includes Chromium and all system deps.

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
```

- [ ] **Step 3: Create `Procfile`**

```
web: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.json
!.env.example
.pytest_cache/
```

- [ ] **Step 5: Create `.env.example`**

```
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=yourpassword
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
SCHEDULER_SECRET=your_secret
DATA_DIR=/data
```

- [ ] **Step 6: Create `config.py`**

```python
import os

def _get(key: str, default: str = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        raise RuntimeError(f"Missing required env var: {key}")
    return val

LINKEDIN_EMAIL       = lambda: _get("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD    = lambda: _get("LINKEDIN_PASSWORD")
ANTHROPIC_API_KEY    = lambda: _get("ANTHROPIC_API_KEY")
TELEGRAM_BOT_TOKEN   = lambda: _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID     = lambda: _get("TELEGRAM_CHAT_ID")
SCHEDULER_SECRET     = lambda: _get("SCHEDULER_SECRET")
DATA_DIR             = lambda: _get("DATA_DIR", "/data")
```

- [ ] **Step 7: Create `database.py`**

```python
import os, json, tempfile
import config

def save_json(path: str, data):
    dir_ = os.path.dirname(path) or "."
    os.makedirs(dir_, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
        tmp = f.name
    os.replace(tmp, path)

def load_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        print(f"[database] JSON decode error in {path}: {e}", flush=True)
        return default

def _data_path(filename: str) -> str:
    d = config.DATA_DIR()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)

def load_state(filename: str, default: dict) -> dict:
    return load_json(_data_path(filename), default=default) or default

def save_state(filename: str, data: dict):
    save_json(_data_path(filename), data)
```

- [ ] **Step 8: Create `telegram_service.py`**

```python
import requests
import config

def send_telegram(message: str):
    token = config.TELEGRAM_BOT_TOKEN()
    chat_id = config.TELEGRAM_CHAT_ID()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=10)
    resp.raise_for_status()
```

- [ ] **Step 9: Write a smoke test and run it**

Create `tests/conftest.py`:
```python
import pytest
import os

@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("LINKEDIN_EMAIL", "test@test.com")
    monkeypatch.setenv("LINKEDIN_PASSWORD", "testpass")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("SCHEDULER_SECRET", "test-secret")
    monkeypatch.setenv("DATA_DIR", "/tmp/linkedin-test")
```

Run: `python -m pytest tests/ -v`
Expected: no errors (no tests yet, just collection)

- [ ] **Step 10: Commit**

```bash
git add .
git commit -m "feat: initial project scaffold"
```

---

### Task 2: LinkedIn Session Service

**Files:**
- Create: `linkedin_session.py`
- Test: `tests/test_linkedin_session.py` (config-only tests, no browser)

- [ ] **Step 1: Create `linkedin_session.py`**

```python
"""
linkedin_session.py — Playwright browser session with anti-detection and cookie persistence.

Usage:
    with LinkedInSession() as session:
        page = session.new_page()
        page.goto("https://www.linkedin.com/feed/")
        session.random_delay()
        # ... do stuff
"""
import time
import random
import os
from playwright.sync_api import sync_playwright, BrowserContext, Page
import database
import config

_COOKIE_FILE = "linkedin_cookies.json"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def random_delay(min_s: float = 1.5, max_s: float = 4.0):
    """Sleep a random human-like amount."""
    time.sleep(random.uniform(min_s, max_s))


class LinkedInSession:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._context: BrowserContext = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ],
        )
        self._context = self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
        # Hide webdriver fingerprint
        self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        self._load_cookies()
        if not self._is_logged_in():
            self._login()
        return self

    def __exit__(self, *args):
        try:
            self._save_cookies()
        except Exception as e:
            print(f"[session] cookie save error: {e}", flush=True)
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def new_page(self) -> Page:
        return self._context.new_page()

    def random_delay(self, min_s: float = 1.5, max_s: float = 4.0):
        random_delay(min_s, max_s)

    def _load_cookies(self):
        cookies = database.load_state(_COOKIE_FILE, default=[])
        if cookies:
            try:
                self._context.add_cookies(cookies)
                print("[session] cookies loaded", flush=True)
            except Exception as e:
                print(f"[session] cookie load error: {e}", flush=True)

    def _save_cookies(self):
        cookies = self._context.cookies()
        database.save_state(_COOKIE_FILE, cookies)
        print("[session] cookies saved", flush=True)

    def _is_logged_in(self) -> bool:
        """Check if current cookies give us an authenticated session."""
        page = self._context.new_page()
        try:
            page.goto("https://www.linkedin.com/feed/", timeout=20000)
            random_delay(2, 4)
            url = page.url
            return "feed" in url or "mynetwork" in url
        except Exception as e:
            print(f"[session] login check error: {e}", flush=True)
            return False
        finally:
            page.close()

    def _login(self):
        """Log in with email/password."""
        print("[session] logging in...", flush=True)
        page = self._context.new_page()
        try:
            page.goto("https://www.linkedin.com/login", timeout=20000)
            random_delay(2, 3)
            page.fill("#username", config.LINKEDIN_EMAIL())
            random_delay(0.5, 1.5)
            page.fill("#password", config.LINKEDIN_PASSWORD())
            random_delay(0.5, 1.5)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle", timeout=15000)
            random_delay(2, 4)
            if "checkpoint" in page.url or "challenge" in page.url:
                print("[session] ⚠️  LinkedIn security challenge detected — manual intervention needed", flush=True)
            elif "feed" in page.url:
                print("[session] login successful", flush=True)
            else:
                print(f"[session] login ended at unexpected URL: {page.url}", flush=True)
        except Exception as e:
            print(f"[session] login error: {e}", flush=True)
            raise
        finally:
            page.close()
```

- [ ] **Step 2: Write config-only test (no browser needed)**

Create `tests/test_linkedin_session.py`:
```python
from unittest.mock import patch, MagicMock
import linkedin_session

def test_random_delay_is_in_range():
    import time
    start = time.time()
    linkedin_session.random_delay(0.05, 0.1)
    elapsed = time.time() - start
    assert 0.05 <= elapsed <= 0.5  # generous upper bound for slow CI

def test_linkedin_session_context_calls_playwright(monkeypatch):
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.cookies.return_value = []
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/feed/"
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context
    mock_pw.chromium.launch.return_value = mock_browser
    mock_sync_pw = MagicMock()
    mock_sync_pw.__enter__ = MagicMock(return_value=mock_pw)
    mock_sync_pw.__exit__ = MagicMock(return_value=False)

    with patch("linkedin_session.sync_playwright", return_value=mock_sync_pw), \
         patch("linkedin_session.database.load_state", return_value=[]), \
         patch("linkedin_session.database.save_state"), \
         patch("linkedin_session.random_delay"):
        with linkedin_session.LinkedInSession() as session:
            assert session is not None
```

- [ ] **Step 3: Run tests**

```bash
python -m pytest tests/test_linkedin_session.py -v
```
Expected: 2 tests PASS

- [ ] **Step 4: Commit**

```bash
git add linkedin_session.py tests/test_linkedin_session.py
git commit -m "feat: add LinkedIn session service with stealth and cookie persistence"
```

---

### Task 3: Co-op Job Scraper

**Files:**
- Create: `job_scraper.py`
- Test: `tests/test_job_scraper.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_scraper.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
import job_scraper

def test_format_job_message():
    job = {
        "title": "Finance Co-op",
        "company": "Fidelity Investments",
        "location": "Boston, MA",
        "url": "https://www.linkedin.com/jobs/view/123",
        "job_id": "123",
    }
    msg = job_scraper.format_job_message(job)
    assert "Finance Co-op" in msg
    assert "Fidelity" in msg
    assert "Boston" in msg
    assert "linkedin.com" in msg

def test_is_new_job_returns_true_for_unseen():
    assert job_scraper.is_new_job("abc123", set()) is True

def test_is_new_job_returns_false_for_seen():
    assert job_scraper.is_new_job("abc123", {"abc123"}) is False

def test_parse_search_url_contains_keywords():
    url = job_scraper.build_search_url(keywords="co-op", location="Boston, MA")
    assert "co-op" in url.lower() or "co%2Dop" in url.lower() or "co+op" in url.lower() or "coop" in url.lower()
    assert "linkedin.com" in url
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
python -m pytest tests/test_job_scraper.py -v
```
Expected: ImportError — job_scraper not defined

- [ ] **Step 3: Create `job_scraper.py`**

```python
"""
job_scraper.py — Scrape LinkedIn Jobs for co-op/internship postings.

Public interface:
    scrape_new_jobs(session: LinkedInSession) -> list[dict]
    format_job_message(job: dict) -> str
    is_new_job(job_id: str, seen_ids: set) -> bool
    build_search_url(keywords: str, location: str) -> str
"""
import urllib.parse
from linkedin_session import LinkedInSession, random_delay
import database

_STATE_FILE = "job_scraper_state.json"
_MAX_SEEN = 2000

_SEARCH_CONFIGS = [
    {"keywords": "co-op finance", "location": "United States"},
    {"keywords": "internship finance", "location": "Boston, MA"},
    {"keywords": "co-op business analyst", "location": "United States"},
    {"keywords": "internship investment banking", "location": "United States"},
]


def build_search_url(keywords: str, location: str) -> str:
    params = urllib.parse.urlencode({
        "keywords": keywords,
        "location": location,
        "f_JT": "I",       # Internship job type
        "f_E": "1,2",      # Entry level + internship
        "sortBy": "DD",    # Date descending
        "f_TPR": "r604800",  # Past week
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
    """Extract job cards from a LinkedIn jobs search page."""
    jobs = []
    try:
        page.wait_for_selector(".jobs-search__results-list", timeout=10000)
    except Exception:
        try:
            page.wait_for_selector(".job-search-card", timeout=5000)
        except Exception:
            print("[job_scraper] no job results found on page", flush=True)
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


def scrape_new_jobs(session: LinkedInSession) -> list:
    """Scrape all search configs, return only unseen jobs. Updates seen state."""
    state = database.load_state(_STATE_FILE, default={"seen_ids": []})
    seen_list = state.get("seen_ids", [])
    seen_set = set(seen_list)

    new_jobs = []
    page = session.new_page()
    try:
        for config in _SEARCH_CONFIGS:
            url = build_search_url(config["keywords"], config["location"])
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
                print(f"[job_scraper] search error for '{config['keywords']}': {e}", flush=True)
    finally:
        page.close()

    state["seen_ids"] = seen_list[-_MAX_SEEN:]
    database.save_state(_STATE_FILE, state)
    print(f"[job_scraper] found {len(new_jobs)} new jobs", flush=True)
    return new_jobs
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_job_scraper.py -v
```
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add job_scraper.py tests/test_job_scraper.py
git commit -m "feat: add co-op job scraper with LinkedIn Jobs search"
```

---

### Task 4: AI Comment Generator

**Files:**
- Create: `ai_service.py`
- Test: `tests/test_ai_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ai_service.py`:
```python
from unittest.mock import patch, MagicMock
import ai_service

def test_generate_comment_returns_string(monkeypatch):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Great perspective on fintech innovation!")]
    mock_client.messages.create.return_value = mock_response

    with patch("ai_service.anthropic.Anthropic", return_value=mock_client):
        result = ai_service.generate_comment(
            post_text="The future of fintech is decentralized.",
            author_name="Jane Smith"
        )
    assert isinstance(result, str)
    assert len(result) > 0

def test_generate_comment_falls_back_on_error(monkeypatch):
    with patch("ai_service.anthropic.Anthropic", side_effect=Exception("API error")):
        result = ai_service.generate_comment("Some post", "Author")
    assert result is None

def test_generate_connection_message_returns_string():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hi! I saw your work in fintech and would love to connect.")]
    mock_client.messages.create.return_value = mock_response

    with patch("ai_service.anthropic.Anthropic", return_value=mock_client):
        result = ai_service.generate_connection_message(
            name="John Doe",
            title="Investment Analyst",
            company="Goldman Sachs"
        )
    assert isinstance(result, str)
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_ai_service.py -v
```
Expected: ImportError

- [ ] **Step 3: Create `ai_service.py`**

```python
"""
ai_service.py — Claude API integration for generating LinkedIn comments and messages.

Public interface:
    generate_comment(post_text, author_name) -> str | None
    generate_connection_message(name, title, company) -> str | None
"""
import anthropic
import config

_PERSONA = (
    "You are a Northeastern University business student (sophomore/junior) "
    "interested in finance, fintech, startups, and entrepreneurship. "
    "You're networking on LinkedIn to build connections for your co-op search. "
    "You are genuine, professional but not stuffy, and curious."
)


def generate_comment(post_text: str, author_name: str) -> str | None:
    """Generate a thoughtful 1-2 sentence comment for a LinkedIn post.
    Returns None on failure.
    """
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"{_PERSONA}\n\n"
            f"Write a short, genuine LinkedIn comment (1-2 sentences max, under 200 chars) "
            f"on this post by {author_name}. Sound human and add value — not generic. "
            f"No hashtags. No 'Great post!' type openers.\n\n"
            f"Post: {post_text[:500]}\n\n"
            f"Comment:"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}]
        )
        comment = response.content[0].text.strip().strip('"')
        return comment if len(comment) > 10 else None
    except Exception as e:
        print(f"[ai_service] generate_comment error: {e}", flush=True)
        return None


def generate_connection_message(name: str, title: str, company: str) -> str | None:
    """Generate a short personalized connection request note (under 300 chars).
    Returns None on failure.
    """
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"{_PERSONA}\n\n"
            f"Write a brief LinkedIn connection request note to {name}, who is a {title} at {company}. "
            f"Under 300 characters. Mention your Northeastern background and genuine interest. "
            f"Professional but warm. No fluff.\n\n"
            f"Note:"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}]
        )
        msg = response.content[0].text.strip().strip('"')
        return msg[:299] if msg else None
    except Exception as e:
        print(f"[ai_service] generate_connection_message error: {e}", flush=True)
        return None
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_ai_service.py -v
```
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add ai_service.py tests/test_ai_service.py
git commit -m "feat: add AI comment and connection message generation"
```

---

### Task 5: Engagement Service

**Files:**
- Create: `engagement_service.py`
- Test: `tests/test_engagement_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_engagement_service.py`:
```python
from unittest.mock import patch, MagicMock
import engagement_service

def test_can_act_returns_true_under_limit():
    state = {"comments": 0, "likes": 0, "date": "2026-03-27"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        assert engagement_service.can_act("comments", state, limit=25) is True

def test_can_act_returns_false_at_limit():
    state = {"comments": 25, "likes": 0, "date": "2026-03-27"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        assert engagement_service.can_act("comments", state, limit=25) is False

def test_can_act_resets_on_new_day():
    state = {"comments": 25, "likes": 50, "date": "2026-03-26"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        assert engagement_service.can_act("comments", state, limit=25) is True

def test_increment_action():
    state = {"comments": 5, "likes": 3, "date": "2026-03-27"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        result = engagement_service.increment_action("comments", state)
    assert result["comments"] == 6

def test_increment_action_resets_on_new_day():
    state = {"comments": 20, "likes": 10, "date": "2026-03-26"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        result = engagement_service.increment_action("comments", state)
    assert result["comments"] == 1
    assert result["date"] == "2026-03-27"
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_engagement_service.py -v
```
Expected: ImportError

- [ ] **Step 3: Create `engagement_service.py`**

```python
"""
engagement_service.py — Like posts, comment on posts, with daily action limits.

Daily limits (conservative to avoid LinkedIn bans):
    comments: 20/day
    likes: 50/day

Public interface:
    engage_hashtag(session, hashtag, max_posts=5) -> dict
    can_act(action, state, limit) -> bool
    increment_action(action, state) -> dict
"""
from datetime import datetime
from zoneinfo import ZoneInfo
from linkedin_session import LinkedInSession, random_delay
import ai_service
import database

_STATE_FILE = "engagement_state.json"
_DAILY_LIMITS = {"comments": 20, "likes": 50}

_TARGET_HASHTAGS = [
    "fintech", "finance", "startups", "entrepreneurship",
    "venturecapital", "privateequity", "business", "northeastern",
]


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _fresh_state() -> dict:
    return {"comments": 0, "likes": 0, "date": _today()}


def can_act(action: str, state: dict, limit: int = None) -> bool:
    """Returns True if we can still perform this action today."""
    if state.get("date") != _today():
        return True  # New day, counts reset
    if limit is None:
        limit = _DAILY_LIMITS.get(action, 999)
    return state.get(action, 0) < limit


def increment_action(action: str, state: dict) -> dict:
    """Increment action count, resetting if it's a new day."""
    today = _today()
    if state.get("date") != today:
        state = {"comments": 0, "likes": 0, "date": today}
    state[action] = state.get(action, 0) + 1
    return state


def _get_post_text(post_el) -> str:
    """Extract text from a feed post element."""
    try:
        text_el = post_el.query_selector(
            ".feed-shared-update-v2__description, "
            ".update-components-text, "
            ".feed-shared-text"
        )
        return (text_el.inner_text() if text_el else "").strip()[:600]
    except Exception:
        return ""


def _get_author_name(post_el) -> str:
    try:
        name_el = post_el.query_selector(
            ".feed-shared-actor__name, "
            ".update-components-actor__name, "
            ".feed-shared-actor__title"
        )
        return (name_el.inner_text() if name_el else "Someone").strip().split("\n")[0]
    except Exception:
        return "Someone"


def engage_hashtag(session: LinkedInSession, hashtag: str, max_posts: int = 5) -> dict:
    """Like and comment on posts from a hashtag feed. Returns counts."""
    state = database.load_state(_STATE_FILE, default=_fresh_state())
    commented = 0
    liked = 0

    page = session.new_page()
    try:
        url = f"https://www.linkedin.com/feed/hashtag/?keywords={hashtag}"
        page.goto(url, timeout=20000)
        random_delay(3, 5)

        posts = page.query_selector_all(
            ".feed-shared-update-v2, .occludable-update"
        )[:max_posts + 3]

        processed = 0
        for post in posts:
            if processed >= max_posts:
                break
            try:
                # Like the post
                if can_act("likes", state):
                    like_btn = post.query_selector(
                        "button[aria-label*='Like'], "
                        "button[aria-label*='like']"
                    )
                    if like_btn and "filled" not in (like_btn.get_attribute("aria-pressed") or ""):
                        like_btn.click()
                        random_delay(1, 2)
                        state = increment_action("likes", state)
                        liked += 1

                # Comment on the post
                if can_act("comments", state):
                    post_text = _get_post_text(post)
                    author = _get_author_name(post)
                    if len(post_text) > 30:  # Only comment on posts with real content
                        comment = ai_service.generate_comment(post_text, author)
                        if comment:
                            comment_btn = post.query_selector(
                                "button[aria-label*='Comment'], "
                                "button[aria-label*='comment']"
                            )
                            if comment_btn:
                                comment_btn.click()
                                random_delay(1, 2)
                                comment_box = page.query_selector(
                                    ".ql-editor[contenteditable='true'], "
                                    ".comments-comment-box__form .ql-editor"
                                )
                                if comment_box:
                                    comment_box.click()
                                    comment_box.type(comment, delay=50)
                                    random_delay(1, 2)
                                    submit_btn = page.query_selector(
                                        "button.comments-comment-box__submit-button, "
                                        "button[type='submit'][form]"
                                    )
                                    if submit_btn:
                                        submit_btn.click()
                                        random_delay(2, 4)
                                        state = increment_action("comments", state)
                                        commented += 1

                processed += 1
                random_delay(5, 12)
            except Exception as e:
                print(f"[engagement] post action error: {e}", flush=True)
                continue

    except Exception as e:
        print(f"[engagement] hashtag page error for #{hashtag}: {e}", flush=True)
    finally:
        page.close()

    database.save_state(_STATE_FILE, state)
    print(f"[engagement] #{hashtag}: liked={liked} commented={commented}", flush=True)
    return {"liked": liked, "commented": commented}


def run_daily_engagement(session: LinkedInSession) -> dict:
    """Run engagement across all target hashtags. Stops if daily limits hit."""
    total = {"liked": 0, "commented": 0}
    state = database.load_state(_STATE_FILE, default=_fresh_state())

    for hashtag in _TARGET_HASHTAGS:
        if not can_act("likes", state) and not can_act("comments", state):
            print("[engagement] daily limits reached, stopping", flush=True)
            break
        result = engage_hashtag(session, hashtag, max_posts=3)
        total["liked"] += result["liked"]
        total["commented"] += result["commented"]
        # Reload state after each hashtag
        state = database.load_state(_STATE_FILE, default=_fresh_state())
        random_delay(15, 30)

    return total
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_engagement_service.py -v
```
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add engagement_service.py tests/test_engagement_service.py
git commit -m "feat: add engagement service with daily limits and hashtag targeting"
```

---

### Task 6: Connector Service

**Files:**
- Create: `connector_service.py`

No unit tests for this — Playwright interactions are the full logic. Tested via manual trigger endpoint.

- [ ] **Step 1: Create `connector_service.py`**

```python
"""
connector_service.py — Find and connect with targeted LinkedIn profiles.

Daily limit: 25 connection requests/day (LinkedIn enforces ~100/week hard limit).

Targeting criteria:
  - Northeastern University students/alumni in business/finance
  - Finance professionals at target companies
  - Startup founders and VCs

Public interface:
    run_daily_connections(session: LinkedInSession) -> int
"""
from linkedin_session import LinkedInSession, random_delay
import ai_service
import database

_STATE_FILE = "connector_state.json"
_DAILY_CONNECT_LIMIT = 20

_SEARCH_QUERIES = [
    {"keywords": "finance co-op Northeastern University", "network": "S,O"},
    {"keywords": "investment banking analyst Boston", "network": "O"},
    {"keywords": "venture capital associate", "network": "O"},
    {"keywords": "fintech startup founder", "network": "O"},
    {"keywords": "Northeastern University DMSB", "network": "S,O"},
]


def _today() -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _get_daily_count(state: dict) -> int:
    if state.get("date") != _today():
        return 0
    return state.get("connects_today", 0)


def _increment_count(state: dict) -> dict:
    today = _today()
    if state.get("date") != today:
        state = {"date": today, "connects_today": 0, "connected_ids": state.get("connected_ids", [])}
    state["connects_today"] = state.get("connects_today", 0) + 1
    return state


def _build_search_url(keywords: str, network: str = "O") -> str:
    import urllib.parse
    params = urllib.parse.urlencode({"keywords": keywords, "network": network, "origin": "GLOBAL_SEARCH_HEADER"})
    return f"https://www.linkedin.com/search/results/people/?{params}"


def run_daily_connections(session: LinkedInSession) -> int:
    """Attempt connection requests up to daily limit. Returns number sent."""
    state = database.load_state(_STATE_FILE, default={"date": _today(), "connects_today": 0, "connected_ids": []})
    connected_ids = set(state.get("connected_ids", []))
    total_sent = 0

    page = session.new_page()
    try:
        for query in _SEARCH_QUERIES:
            daily_count = _get_daily_count(state)
            if daily_count >= _DAILY_CONNECT_LIMIT:
                print("[connector] daily limit reached", flush=True)
                break

            url = _build_search_url(query["keywords"], query.get("network", "O"))
            try:
                page.goto(url, timeout=20000)
                random_delay(3, 5)

                results = page.query_selector_all(".reusable-search__result-container")[:8]
                for result in results:
                    if _get_daily_count(state) >= _DAILY_CONNECT_LIMIT:
                        break
                    try:
                        # Get profile info
                        name_el = result.query_selector(".entity-result__title-text a span[aria-hidden='true']")
                        title_el = result.query_selector(".entity-result__primary-subtitle")
                        profile_link = result.query_selector("a.app-aware-link[href*='/in/']")

                        if not name_el or not profile_link:
                            continue

                        name = name_el.inner_text().strip()
                        title = (title_el.inner_text() if title_el else "").strip()
                        profile_url = profile_link.get_attribute("href") or ""
                        profile_id = profile_url.split("/in/")[1].split("/")[0].split("?")[0] if "/in/" in profile_url else ""

                        if not profile_id or profile_id in connected_ids:
                            continue

                        # Look for Connect button
                        connect_btn = result.query_selector(
                            "button[aria-label*='Connect'], "
                            "button[aria-label*='Invite']"
                        )
                        if not connect_btn:
                            continue

                        connect_btn.click()
                        random_delay(1, 2)

                        # Check if "Add a note" option is available
                        add_note_btn = page.query_selector("button[aria-label='Add a note']")
                        if add_note_btn:
                            company = title.split(" at ")[-1] if " at " in title else ""
                            role = title.split(" at ")[0] if " at " in title else title
                            note = ai_service.generate_connection_message(name, role, company)
                            if note:
                                add_note_btn.click()
                                random_delay(0.5, 1)
                                note_box = page.query_selector("textarea#custom-message")
                                if note_box:
                                    note_box.fill(note)
                                    random_delay(0.5, 1)

                        # Click Send
                        send_btn = page.query_selector(
                            "button[aria-label='Send now'], "
                            "button[aria-label='Send invitation']"
                        )
                        if send_btn:
                            send_btn.click()
                            random_delay(2, 4)
                            connected_ids.add(profile_id)
                            state = _increment_count(state)
                            state["connected_ids"] = list(connected_ids)[-2000:]
                            total_sent += 1
                            print(f"[connector] connected with {name}", flush=True)
                        else:
                            # Close modal if send failed
                            dismiss = page.query_selector("button[aria-label='Dismiss']")
                            if dismiss:
                                dismiss.click()

                        random_delay(8, 15)
                    except Exception as e:
                        print(f"[connector] person action error: {e}", flush=True)
                        continue

                random_delay(10, 20)
            except Exception as e:
                print(f"[connector] search error: {e}", flush=True)
                continue
    finally:
        page.close()
        database.save_state(_STATE_FILE, state)

    print(f"[connector] sent {total_sent} connection requests today", flush=True)
    return total_sent
```

- [ ] **Step 2: Run all tests to make sure nothing broke**

```bash
python -m pytest tests/ -v
```
Expected: all existing tests PASS

- [ ] **Step 3: Commit**

```bash
git add connector_service.py
git commit -m "feat: add auto-connector with targeted search and AI personalized notes"
```

---

### Task 7: Flask App + Endpoints

**Files:**
- Create: `app.py`
- Test: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_app.py`:
```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    import app as application
    application.app.config["TESTING"] = True
    with application.app.test_client() as c:
        yield c

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200

def test_job_scraper_rejects_bad_secret(client):
    res = client.post("/internal/run-job-scraper?secret=wrong")
    assert res.status_code == 403

def test_engagement_rejects_bad_secret(client):
    res = client.post("/internal/run-engagement?secret=wrong")
    assert res.status_code == 403

def test_connector_rejects_bad_secret(client):
    res = client.post("/internal/run-connector?secret=wrong")
    assert res.status_code == 403

def test_job_scraper_returns_ok(client, monkeypatch):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-job-scraper?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"

def test_engagement_returns_ok(client, monkeypatch):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-engagement?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"

def test_connector_returns_ok(client, monkeypatch):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-connector?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"
```

- [ ] **Step 2: Run to confirm failure**

```bash
python -m pytest tests/test_app.py -v
```
Expected: ImportError

- [ ] **Step 3: Create `app.py`**

```python
from flask import Flask, request, jsonify
import threading
import config

app = Flask(__name__)


def _run_job_scraper():
    from linkedin_session import LinkedInSession
    from job_scraper import scrape_new_jobs, format_job_message
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            jobs = scrape_new_jobs(session)
        if not jobs:
            print("[job_scraper] no new jobs found", flush=True)
            return
        header = f"💼 {len(jobs)} new co-op/internship listings:\n"
        send_telegram(header + "\n\n".join(format_job_message(j) for j in jobs[:10]))
        print(f"[job_scraper] sent {len(jobs)} jobs to Telegram", flush=True)
    except Exception as e:
        print(f"[job_scraper] run error: {e}", flush=True)


def _run_engagement():
    from linkedin_session import LinkedInSession
    from engagement_service import run_daily_engagement
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            result = run_daily_engagement(session)
        send_telegram(f"✅ LinkedIn engagement done: {result['liked']} likes, {result['commented']} comments")
    except Exception as e:
        print(f"[engagement] run error: {e}", flush=True)


def _run_connector():
    from linkedin_session import LinkedInSession
    from connector_service import run_daily_connections
    from telegram_service import send_telegram
    try:
        with LinkedInSession() as session:
            count = run_daily_connections(session)
        send_telegram(f"🤝 LinkedIn connector done: {count} connection requests sent")
    except Exception as e:
        print(f"[connector] run error: {e}", flush=True)


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/internal/run-job-scraper", methods=["POST"])
def run_job_scraper():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_job_scraper, daemon=True).start()
    return jsonify({"status": "ok", "message": "job scraper started"})


@app.route("/internal/run-engagement", methods=["POST"])
def run_engagement():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_engagement, daemon=True).start()
    return jsonify({"status": "ok", "message": "engagement started"})


@app.route("/internal/run-connector", methods=["POST"])
def run_connector():
    secret = request.args.get("secret", "")
    if secret != config.SCHEDULER_SECRET():
        return "Forbidden", 403
    threading.Thread(target=_run_connector, daemon=True).start()
    return jsonify({"status": "ok", "message": "connector started"})


if __name__ == "__main__":
    app.run(debug=True)
```

- [ ] **Step 4: Run all tests**

```bash
python -m pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add Flask app with job scraper, engagement, and connector endpoints"
```

---

### Task 8: Railway Deployment

**Files:**
- No new files — just configure Railway and cron jobs

- [ ] **Step 1: Create GitHub repo and push**

```bash
git remote add origin https://github.com/sebbycast106-art/linkedin-bot.git
git push -u origin main
```

- [ ] **Step 2: Set Railway env vars**

In Railway dashboard → New Project → Deploy from GitHub → select `linkedin-bot`:

| Variable | Value |
|---|---|
| `LINKEDIN_EMAIL` | your LinkedIn email |
| `LINKEDIN_PASSWORD` | your LinkedIn password |
| `ANTHROPIC_API_KEY` | same as assistant bot |
| `TELEGRAM_BOT_TOKEN` | same as assistant bot |
| `TELEGRAM_CHAT_ID` | same as assistant bot |
| `SCHEDULER_SECRET` | same as assistant bot (or new one) |
| `DATA_DIR` | `/data` |

Also add a Railway Volume mounted at `/data` for persistent state.

- [ ] **Step 3: Verify deployment**

```bash
curl https://your-railway-url.up.railway.app/health
```
Expected: `{"status": "ok"}`

- [ ] **Step 4: Set up cron jobs on cron-job.org**

Use the API (already have key). Schedule:

| Endpoint | Schedule | Description |
|---|---|---|
| `/internal/run-job-scraper` | `0 9 * * *` | Daily 9 AM ET job scan |
| `/internal/run-engagement` | `0 11 * * 1,2,3,4,5` | Weekdays 11 AM ET |
| `/internal/run-connector` | `0 10 * * 1,3,5` | Mon/Wed/Fri 10 AM ET |

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "chore: deployment ready"
git push origin main
```
