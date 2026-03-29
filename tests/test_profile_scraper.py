"""Tests for profile_scraper.scrape_profile."""
import pytest
from unittest.mock import MagicMock, patch

from profile_scraper import scrape_profile


def make_page(selectors: dict):
    """selectors maps CSS selector -> inner_text string or None"""
    page = MagicMock()
    page.goto = MagicMock()

    def query_selector(sel):
        text = selectors.get(sel)
        if text is None:
            return None
        el = MagicMock()
        el.inner_text.return_value = text
        return el

    page.query_selector.side_effect = query_selector
    return page


URL = "https://www.linkedin.com/in/testuser"


@patch("linkedin_session.random_delay", return_value=None)
def test_scrape_profile_full(mock_delay):
    page = make_page({
        ".text-body-medium.break-words": "Software Engineer at Acme",
        ".pv-text-details__right-panel .hoverable-link-text": "Acme Corp",
        ".pv-education-entity .pv-entity__school-name": "MIT",
        ".pv-text-details__left-panel .text-body-small": "San Francisco, CA",
        ".member-connections": "42 mutual connections",
    })
    result = scrape_profile(page, URL)
    assert result["headline"] == "Software Engineer at Acme"
    assert result["company"] == "Acme Corp"
    assert result["school"] == "MIT"
    assert result["location"] == "San Francisco, CA"


@patch("linkedin_session.random_delay", return_value=None)
def test_scrape_profile_partial(mock_delay):
    # Only headline and location present; company and school return None
    page = make_page({
        ".text-body-medium.break-words": "Product Manager",
        ".pv-text-details__left-panel .text-body-small": "New York, NY",
    })
    result = scrape_profile(page, URL)
    assert "headline" in result
    assert "location" in result
    assert "company" not in result
    assert "school" not in result


@patch("linkedin_session.random_delay", return_value=None)
def test_scrape_profile_returns_empty_on_exception(mock_delay):
    page = MagicMock()
    page.goto.side_effect = Exception("network error")
    result = scrape_profile(page, URL)
    assert result == {}


@patch("linkedin_session.random_delay", return_value=None)
def test_scrape_profile_mutual_count_parsed(mock_delay):
    page = make_page({
        ".member-connections": "42 mutual connections",
    })
    result = scrape_profile(page, URL)
    assert result.get("mutual_count") == 42


@patch("linkedin_session.random_delay", return_value=None)
def test_scrape_profile_mutual_count_missing(mock_delay):
    # .member-connections not present
    page = make_page({
        ".text-body-medium.break-words": "Designer",
    })
    result = scrape_profile(page, URL)
    assert "mutual_count" not in result
