"""
feed_scraper_service.py — Scrape LinkedIn feed posts and save them as a log.

Keeps the 100 most recent posts, deduped by content hash.
Scrapes from the main feed + target hashtags.

Public interface:
    run_feed_scrape(session) -> dict  # {"scraped": N, "new": N}
    get_posts(limit=50) -> list
"""
import hashlib
from datetime import datetime, timezone

import database
from linkedin_session import LinkedInSession, random_delay

_STATE_FILE = "feed_posts.json"
_MAX_POSTS = 100
_HASHTAGS = ["fintech", "finance", "venturecapital", "northeastern"]


def _post_id(author: str, text: str) -> str:
    return hashlib.md5(f"{author}:{text[:120]}".encode()).hexdigest()[:16]


def _extract_posts(page) -> list:
    posts = []
    try:
        els = page.query_selector_all(".feed-shared-update-v2, .occludable-update")[:15]
        for el in els:
            try:
                # Author
                name_el = el.query_selector(
                    ".feed-shared-actor__name, .update-components-actor__name"
                )
                author = (name_el.inner_text().strip().split("\n")[0] if name_el else "").strip()

                # Headline
                headline_el = el.query_selector(
                    ".feed-shared-actor__description, .update-components-actor__description"
                )
                headline = (headline_el.inner_text().strip().split("\n")[0] if headline_el else "").strip()

                # Text
                text_el = el.query_selector(
                    ".feed-shared-update-v2__description, .update-components-text, .feed-shared-text"
                )
                text = (text_el.inner_text().strip() if text_el else "").strip()[:800]

                if not author or not text:
                    continue

                # Reaction count
                reactions = 0
                try:
                    react_el = el.query_selector(
                        ".social-details-social-counts__reactions-count, "
                        ".social-details-social-counts__count-value"
                    )
                    if react_el:
                        raw = react_el.inner_text().strip().replace(",", "")
                        reactions = int(raw) if raw.isdigit() else 0
                except Exception:
                    pass

                # Post URL
                post_url = ""
                try:
                    link_el = el.query_selector("a[href*='/posts/'], a[href*='/feed/update/']")
                    if link_el:
                        post_url = link_el.get_attribute("href") or ""
                        if post_url and not post_url.startswith("http"):
                            post_url = "https://www.linkedin.com" + post_url
                except Exception:
                    pass

                posts.append({
                    "id": _post_id(author, text),
                    "author": author,
                    "headline": headline,
                    "text": text,
                    "reactions": reactions,
                    "url": post_url,
                    "scraped_at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                continue
    except Exception:
        pass
    return posts


def run_feed_scrape(session: LinkedInSession) -> dict:
    state = database.load_state(_STATE_FILE, default={"posts": []})
    existing = {p["id"]: p for p in state.get("posts", [])}
    new_count = 0

    page = session.new_page()
    try:
        # Scrape main feed
        page.goto("https://www.linkedin.com/feed/", timeout=20000)
        random_delay(3, 5)
        for post in _extract_posts(page):
            if post["id"] not in existing:
                existing[post["id"]] = post
                new_count += 1

        # Scrape top hashtags
        for tag in _HASHTAGS[:2]:
            try:
                page.goto(f"https://www.linkedin.com/feed/hashtag/?keywords={tag}", timeout=15000)
                random_delay(2, 4)
                for post in _extract_posts(page):
                    if post["id"] not in existing:
                        existing[post["id"]] = post
                        new_count += 1
            except Exception:
                pass

    except Exception as e:
        print(f"[feed_scraper] error: {e}", flush=True)
    finally:
        try:
            page.close()
        except Exception:
            pass

    # Sort by scraped_at descending, keep latest _MAX_POSTS
    all_posts = sorted(existing.values(), key=lambda p: p.get("scraped_at", ""), reverse=True)
    all_posts = all_posts[:_MAX_POSTS]

    state["posts"] = all_posts
    state["last_scraped"] = datetime.now(timezone.utc).isoformat()
    database.save_state(_STATE_FILE, state)

    print(f"[feed_scraper] total={len(all_posts)} new={new_count}", flush=True)
    return {"scraped": len(all_posts), "new": new_count}


def get_posts(limit: int = 50) -> list:
    state = database.load_state(_STATE_FILE, default={"posts": []})
    return state.get("posts", [])[:limit]
