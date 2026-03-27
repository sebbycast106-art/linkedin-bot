"""
engagement_service.py — Like and comment on LinkedIn posts by hashtag with daily limits.

Daily limits: comments=20/day, likes=50/day

Public interface:
    engage_hashtag(session, hashtag, max_posts=5) -> dict
    run_daily_engagement(session) -> dict
    can_act(action, state, limit=None) -> bool
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
    "venturecapital", "business", "northeastern",
]


def _today() -> str:
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def _fresh_state() -> dict:
    return {"comments": 0, "likes": 0, "date": _today()}


def can_act(action: str, state: dict, limit: int = None) -> bool:
    if state.get("date") != _today():
        return True
    if limit is None:
        limit = _DAILY_LIMITS.get(action, 999)
    return state.get(action, 0) < limit


def increment_action(action: str, state: dict) -> dict:
    today = _today()
    if state.get("date") != today:
        state = {"comments": 0, "likes": 0, "date": today}
    state[action] = state.get(action, 0) + 1
    return state


def _get_post_text(post_el) -> str:
    try:
        text_el = post_el.query_selector(
            ".feed-shared-update-v2__description, .update-components-text, .feed-shared-text"
        )
        return (text_el.inner_text() if text_el else "").strip()[:600]
    except Exception:
        return ""


def _get_author_name(post_el) -> str:
    try:
        name_el = post_el.query_selector(
            ".feed-shared-actor__name, .update-components-actor__name"
        )
        return (name_el.inner_text() if name_el else "Someone").strip().split("\n")[0]
    except Exception:
        return "Someone"


def engage_hashtag(session: LinkedInSession, hashtag: str, max_posts: int = 5) -> dict:
    state = database.load_state(_STATE_FILE, default=_fresh_state())
    commented = 0
    liked = 0

    page = session.new_page()
    try:
        page.goto(f"https://www.linkedin.com/feed/hashtag/?keywords={hashtag}", timeout=20000)
        random_delay(3, 5)

        posts = page.query_selector_all(".feed-shared-update-v2, .occludable-update")[:max_posts + 3]
        processed = 0

        for post in posts:
            if processed >= max_posts:
                break
            try:
                if can_act("likes", state):
                    like_btn = post.query_selector("button[aria-label*='Like'], button[aria-label*='like']")
                    if like_btn and "filled" not in (like_btn.get_attribute("aria-pressed") or ""):
                        like_btn.click()
                        random_delay(1, 2)
                        state = increment_action("likes", state)
                        liked += 1

                if can_act("comments", state):
                    post_text = _get_post_text(post)
                    author = _get_author_name(post)
                    if len(post_text) > 30:
                        comment = ai_service.generate_comment(post_text, author)
                        if comment:
                            comment_btn = post.query_selector("button[aria-label*='Comment'], button[aria-label*='comment']")
                            if comment_btn:
                                comment_btn.click()
                                random_delay(1, 2)
                                comment_box = page.query_selector(".ql-editor[contenteditable='true']")
                                if comment_box:
                                    comment_box.click()
                                    comment_box.type(comment, delay=50)
                                    random_delay(1, 2)
                                    submit_btn = page.query_selector("button.comments-comment-box__submit-button")
                                    if submit_btn:
                                        submit_btn.click()
                                        random_delay(2, 4)
                                        state = increment_action("comments", state)
                                        commented += 1

                processed += 1
                random_delay(5, 12)
            except Exception as e:
                print(f"[engagement] post error: {e}", flush=True)
    except Exception as e:
        print(f"[engagement] hashtag #{hashtag} error: {e}", flush=True)
    finally:
        page.close()

    database.save_state(_STATE_FILE, state)
    print(f"[engagement] #{hashtag}: liked={liked} commented={commented}", flush=True)
    return {"liked": liked, "commented": commented}


def run_daily_engagement(session: LinkedInSession) -> dict:
    total = {"liked": 0, "commented": 0}
    state = database.load_state(_STATE_FILE, default=_fresh_state())

    for hashtag in _TARGET_HASHTAGS:
        if not can_act("likes", state) and not can_act("comments", state):
            print("[engagement] daily limits reached", flush=True)
            break
        result = engage_hashtag(session, hashtag, max_posts=3)
        total["liked"] += result["liked"]
        total["commented"] += result["commented"]
        state = database.load_state(_STATE_FILE, default=_fresh_state())
        random_delay(15, 30)

    return total
