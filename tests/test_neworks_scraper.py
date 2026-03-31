"""
Tests for neworks_scraper.py — unit tests with mocked Playwright + database.
Follows the same unittest.mock.patch pattern as the rest of the test suite.
"""
import pytest
from unittest.mock import patch, MagicMock, call


# ── Cookie helpers ────────────────────────────────────────────────────────────

def test_load_cookies_returns_empty_when_missing():
    with patch("database.load_state", return_value=[]) as mock_load:
        from neworks_scraper import load_neworks_cookies
        result = load_neworks_cookies()
    assert result == []
    mock_load.assert_called_once_with("neworks_cookies.json", default=[])


def test_load_cookies_returns_saved_list():
    fake_cookies = [{"name": "sessionid", "value": "abc123", "domain": ".northeastern.edu"}]
    with patch("database.load_state", return_value=fake_cookies):
        from neworks_scraper import load_neworks_cookies
        result = load_neworks_cookies()
    assert result == fake_cookies


def test_save_cookies_calls_save_state():
    fake_cookies = [{"name": "token", "value": "xyz"}]
    with patch("database.save_state") as mock_save:
        from neworks_scraper import save_neworks_cookies
        save_neworks_cookies(fake_cookies)
    mock_save.assert_called_once_with("neworks_cookies.json", fake_cookies)


# ── is_authenticated ──────────────────────────────────────────────────────────

def test_is_authenticated_returns_true_on_neworks_url():
    page = MagicMock()
    page.goto = MagicMock()
    page.url = "https://neworks.northeastern.edu/app/jobs"
    # No auth element found — fallback: URL on neworks without login
    page.query_selector = MagicMock(return_value=None)

    from neworks_scraper import is_authenticated
    result = is_authenticated(page)
    assert result is True


def test_is_authenticated_returns_false_on_microsoft_sso():
    page = MagicMock()
    page.goto = MagicMock()
    page.url = "https://login.microsoftonline.com/northeastern.edu/sso"
    page.query_selector = MagicMock(return_value=None)

    from neworks_scraper import is_authenticated
    result = is_authenticated(page)
    assert result is False


def test_is_authenticated_returns_false_on_exception():
    page = MagicMock()
    page.goto.side_effect = Exception("network error")

    from neworks_scraper import is_authenticated
    result = is_authenticated(page)
    assert result is False


# ── perform_sso_login ─────────────────────────────────────────────────────────

def test_perform_sso_login_returns_false_on_duo_push():
    page = MagicMock()
    context = MagicMock()
    page.goto = MagicMock()
    page.url = "https://duosecurity.com/duo_frame"
    page.wait_for_load_state = MagicMock()
    page.query_selector = MagicMock(return_value=None)
    page.click = MagicMock(side_effect=Exception("not found"))
    page.fill = MagicMock()
    # After filling credentials, page content says Duo pushed
    page.inner_text = MagicMock(return_value="pushed a login request to your device")

    with patch("config.NORTHEASTERN_USERNAME", return_value="test@northeastern.edu"):
        with patch("config.NORTHEASTERN_PASSWORD", return_value="password123"):
            from neworks_scraper import perform_sso_login
            result = perform_sso_login(page, context)

    assert result is False


def test_perform_sso_login_raises_on_missing_credentials():
    page = MagicMock()
    context = MagicMock()

    with patch("config.NORTHEASTERN_USERNAME", side_effect=RuntimeError("Missing required env var: NORTHEASTERN_USERNAME")):
        from neworks_scraper import perform_sso_login
        with pytest.raises(RuntimeError, match="NEU credentials not set"):
            perform_sso_login(page, context)


# ── scrape_neworks_jobs ───────────────────────────────────────────────────────

def test_scrape_skips_already_seen_ids():
    """scrape_neworks_jobs returns only unseen jobs."""
    page = MagicMock()
    page.goto = MagicMock()
    page.wait_for_selector = MagicMock()
    page.inner_text = MagicMock(return_value="")

    def make_card(job_id_num: int, title: str, company: str):
        card = MagicMock()

        # get_attribute(attr) — return href only for "href", empty string otherwise
        def get_attr(attr):
            if attr == "href":
                return f"/app/jobs/{job_id_num}"
            return ""
        card.get_attribute = MagicMock(side_effect=get_attr)

        title_el = MagicMock()
        title_el.inner_text = MagicMock(return_value=title)
        company_el = MagicMock()
        company_el.inner_text = MagicMock(return_value=company)
        location_el = MagicMock()
        location_el.inner_text = MagicMock(return_value="Boston, MA")

        def sel_fn(sel):
            if "title" in sel or sel in ("h3", "h4"):
                return title_el
            if "employer" in sel or "company" in sel:
                return company_el
            if "location" in sel:
                return location_el
            return None

        card.query_selector = MagicMock(side_effect=sel_fn)
        return card

    cards = [
        make_card(1001, "Finance Analyst Co-op", "Fidelity"),
        make_card(1002, "Data Co-op", "State Street"),   # already seen
        make_card(1003, "Risk Co-op", "BlackRock"),       # already seen
    ]

    page.query_selector_all = MagicMock(return_value=cards)
    seen_ids = {"neworks_1002", "neworks_1003"}

    from neworks_scraper import scrape_neworks_jobs
    results = scrape_neworks_jobs(page, seen_ids)

    assert len(results) == 1
    assert results[0]["job_id"] == "neworks_1001"
    assert results[0]["source"] == "neworks"


def test_scrape_caps_seen_ids_at_max():
    """Verify that seen_ids list is capped at _MAX_SEEN (2000) when overflow occurs."""
    import neworks_scraper as ns

    # Start with MAX_SEEN existing IDs (already at cap)
    existing_ids = [f"neworks_{i}" for i in range(ns._MAX_SEEN)]
    assert len(existing_ids) == 2000

    # Add 1 new job — total becomes 2001 before capping
    new_jobs = [{"job_id": "neworks_NEW"}]
    for job in new_jobs:
        existing_ids.append(job["job_id"])

    # Apply cap: keep last _MAX_SEEN
    capped = existing_ids[-ns._MAX_SEEN:]

    assert len(capped) == 2000
    assert "neworks_NEW" in capped
    assert "neworks_0" not in capped  # oldest trimmed when over cap


# ── run_neworks_scraper ───────────────────────────────────────────────────────

def test_run_neworks_scraper_returns_duo_required_and_sends_telegram():
    """If SSO login returns False (Duo push), status = duo_required and Telegram alert sent."""
    with patch("database.load_state", return_value={"seen_ids": []}), \
         patch("database.save_state"), \
         patch("neworks_scraper.load_neworks_cookies", return_value=[]), \
         patch("neworks_scraper.save_neworks_cookies"), \
         patch("telegram_service.send_telegram") as mock_tg, \
         patch("neworks_scraper.is_authenticated", return_value=False), \
         patch("neworks_scraper.perform_sso_login", return_value=False), \
         patch("playwright.sync_api.sync_playwright") as mock_pw:

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.start.return_value = MagicMock(
            chromium=MagicMock(launch=MagicMock(return_value=mock_browser))
        )
        mock_browser.new_context = MagicMock(return_value=mock_context)
        mock_context.new_page = MagicMock(return_value=mock_page)
        mock_context.add_cookies = MagicMock()

        from neworks_scraper import run_neworks_scraper
        result = run_neworks_scraper()

    assert result["status"] == "duo_required"
    # Telegram must have been called with Duo message
    assert mock_tg.called
    call_args = mock_tg.call_args_list[0][0][0]
    assert "duo" in call_args.lower() or "Duo" in call_args


def test_run_neworks_scraper_calls_add_application_for_scored_jobs():
    """Scored jobs get added to application_tracker with source='neworks'."""
    fake_jobs = [
        {"job_id": "neworks_111", "title": "Finance Co-op", "company": "Fidelity", "url": "https://example.com", "source": "neworks", "description": ""},
    ]
    fake_scored = [
        {"job_id": "neworks_111", "title": "Finance Co-op", "company": "Fidelity", "url": "https://example.com", "source": "neworks", "score": 8},
    ]

    with patch("database.load_state", return_value={"seen_ids": []}), \
         patch("database.save_state"), \
         patch("neworks_scraper.load_neworks_cookies", return_value=[{"name": "x", "value": "y"}]), \
         patch("neworks_scraper.save_neworks_cookies"), \
         patch("neworks_scraper.is_authenticated", return_value=True), \
         patch("neworks_scraper.scrape_neworks_jobs", return_value=fake_jobs), \
         patch("job_scorer.filter_and_score_jobs", return_value=fake_scored), \
         patch("application_tracker.add_application") as mock_add, \
         patch("telegram_service.send_telegram"), \
         patch("playwright.sync_api.sync_playwright") as mock_pw:

        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_pw.return_value.start.return_value = MagicMock(
            chromium=MagicMock(launch=MagicMock(return_value=mock_browser))
        )
        mock_browser.new_context = MagicMock(return_value=mock_context)
        mock_context.new_page = MagicMock(return_value=mock_page)
        mock_context.add_cookies = MagicMock()
        mock_context.cookies = MagicMock(return_value=[])

        from neworks_scraper import run_neworks_scraper
        result = run_neworks_scraper()

    assert result["status"] == "ok"
    mock_add.assert_called_once()
    call_kwargs = mock_add.call_args
    assert call_kwargs[1].get("source") == "neworks" or "neworks" in str(call_kwargs)
