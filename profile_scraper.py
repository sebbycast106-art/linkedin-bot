"""
profile_scraper.py — Scrape a LinkedIn profile page for enrichment data.

Public interface:
    scrape_profile(page, url) -> dict
"""
import re
import linkedin_session


def scrape_profile(page, url: str) -> dict:
    try:
        page.goto(url, timeout=15000)
        linkedin_session.random_delay(2, 3)

        result = {}

        # headline
        for sel in [
            ".text-body-medium.break-words",
            ".pv-text-details__left-panel .text-body-medium",
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    result["headline"] = text
                    break

        # company
        for sel in [
            ".pv-text-details__right-panel .hoverable-link-text",
            ".pv-profile-section__card-item-v2 .pv-entity__secondary-title",
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    result["company"] = text
                    break

        # school
        for sel in [
            ".pv-education-entity .pv-entity__school-name",
            ".education-section .pv-entity__school-name",
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    result["school"] = text
                    break

        # location
        for sel in [
            ".pv-text-details__left-panel .text-body-small",
            ".pv-top-card--list-bullet li",
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if text:
                    result["location"] = text
                    break

        # mutual_count
        el = page.query_selector(".member-connections")
        if el:
            text = el.inner_text()
            m = re.search(r"(\d+)\s+mutual", text)
            if m:
                result["mutual_count"] = int(m.group(1))

        print(f"[profile_scraper] scraped {url[:50]}: {list(result.keys())}", flush=True)
        return result

    except Exception as e:
        print(f"[profile_scraper] error scraping {url[:50]}: {e}", flush=True)
        return {}
