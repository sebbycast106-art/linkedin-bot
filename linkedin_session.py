"""
linkedin_session.py — Playwright browser session with anti-detection and cookie persistence.

Usage:
    with LinkedInSession() as session:
        page = session.new_page()
        page.goto("https://www.linkedin.com/feed/")
        session.random_delay()
"""
import time
import random
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
                "--no-zygote",
                "--single-process",
            ],
        )
        self._context = self._browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1366, "height": 768},
            locale="en-US",
        )
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
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
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
            except Exception as e:
                print(f"[session] cookie load error: {e}", flush=True)

    def _save_cookies(self):
        cookies = self._context.cookies()
        database.save_state(_COOKIE_FILE, cookies)

    def _is_logged_in(self) -> bool:
        page = self._context.new_page()
        try:
            page.goto("https://www.linkedin.com/feed/", timeout=20000)
            random_delay(2, 4)
            return "feed" in page.url or "mynetwork" in page.url
        except Exception:
            return False
        finally:
            page.close()

    def _login(self):
        print("[session] logging in...", flush=True)
        page = self._context.new_page()
        try:
            page.goto("https://www.linkedin.com/login", timeout=20000)
            random_delay(2, 3)
            page.fill("#username", config.LINKEDIN_EMAIL())
            random_delay(1.0, 2.5)
            page.fill("#password", config.LINKEDIN_PASSWORD())
            random_delay(1.0, 2.5)
            page.click("button[type='submit']")
            page.wait_for_load_state("networkidle", timeout=15000)
            random_delay(2, 4)
            if "checkpoint" in page.url or "challenge" in page.url:
                database.save_state("linkedin_challenge_state.json", {
                    "challenge_url": page.url,
                    "cookies": self._context.cookies(),
                    "detected_at": time.time(),
                })
                msg = (
                    f"⚠️ LinkedIn security challenge detected!\n"
                    f"URL: {page.url}\n\n"
                    f"Check your email for a 6-digit code, then call:\n"
                    f"POST /internal/linkedin-verify with body {{\"code\": \"XXXXXX\"}}\n\n"
                    f"Or POST /internal/linkedin-reset to clear state and start fresh."
                )
                print(f"[session] {msg}", flush=True)
                try:
                    import telegram_service
                    telegram_service.send_telegram(msg)
                except Exception:
                    pass
                raise RuntimeError(f"LinkedIn security challenge: {page.url}")
            else:
                print(f"[session] login result: {page.url}", flush=True)
        except Exception as e:
            print(f"[session] login error: {e}", flush=True)
            raise
        finally:
            page.close()
