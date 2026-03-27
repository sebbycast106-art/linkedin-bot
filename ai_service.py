"""
ai_service.py — Claude API for generating LinkedIn comments and connection messages.

Public interface:
    generate_comment(post_text, author_name) -> str | None
    generate_connection_message(name, title, company) -> str | None
"""
import anthropic
import config

_PERSONA = (
    "You are a Northeastern University business student (sophomore) "
    "interested in finance, fintech, startups, and entrepreneurship. "
    "You're networking on LinkedIn to build connections for your co-op search. "
    "You are genuine, professional but not stuffy, and curious."
)


def generate_comment(post_text: str, author_name: str) -> str | None:
    """Generate a thoughtful 1-2 sentence comment. Returns None on failure."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"{_PERSONA}\n\n"
            f"Write a short, genuine LinkedIn comment (1-2 sentences max, under 200 chars) "
            f"on this post by {author_name}. Sound human and add value — not generic. "
            f"No hashtags. No 'Great post!' type openers.\n\n"
            f"Post: {post_text[:500]}\n\nComment:"
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
    """Generate a short personalized connection request note (under 300 chars). Returns None on failure."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"{_PERSONA}\n\n"
            f"Write a brief LinkedIn connection request note to {name}, who is a {title} at {company}. "
            f"Under 300 characters. Mention Northeastern and genuine interest. Professional but warm. No fluff.\n\nNote:"
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
