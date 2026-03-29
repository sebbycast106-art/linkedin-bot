"""
ai_service.py — Claude API for generating LinkedIn comments and connection messages.

Public interface:
    generate_comment(post_text, author_name) -> str | None
    generate_connection_message(name, title, company, *, school="", headline="") -> str | None
    generate_recruiter_followup_message(name, company) -> str | None
    generate_inbox_reply(sender_name, sender_title, message_text) -> str | None
    generate_cover_letter(title, company, description) -> str | None
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


def generate_connection_message(name: str, title: str, company: str, *, school: str = "", headline: str = "") -> str | None:
    """Generate a short personalized connection request note (under 300 chars). Returns None on failure."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        extra = (
            ("School: " + school + ". " if school else "") +
            ("Headline: " + headline + ". " if headline else "")
        )
        prompt = (
            f"{_PERSONA}\n\n"
            f"Write a brief LinkedIn connection request note to {name}, who is a {title} at {company}. "
            f"{extra}"
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


def generate_recruiter_followup_message(name: str, company: str) -> str | None:
    """Generate a short follow-up message (under 300 chars) to send after a recruiter accepts your connection. Returns None on failure."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"{_PERSONA}\n\n"
            f"Write a brief LinkedIn follow-up message to {name} at {company}, who just accepted your connection request. "
            f"Mention you're a Northeastern sophomore looking for finance/fintech co-ops, reference their company, "
            f"and ask if they have any openings or advice. Under 300 characters. Conversational, not spammy.\n\nMessage:"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}]
        )
        msg = response.content[0].text.strip().strip('"')
        return msg[:299] if msg else None
    except Exception as e:
        print(f"[ai_service] generate_recruiter_followup_message error: {e}", flush=True)
        return None


def generate_cover_letter(title: str, company: str, description: str) -> str | None:
    """Generate a short cover letter paragraph for a job application."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = f"""Write a 3-sentence cover letter paragraph for a Northeastern University sophomore applying for this role. Be specific, professional, and mention relevant skills. Do NOT start with "Dear" or "To Whom".

Title: {title}
Company: {company}
Description: {description[:800]}

Reply with ONLY the cover letter paragraph. Nothing else."""
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[ai_service] cover letter error: {e}", flush=True)
        return None


def generate_inbox_reply(sender_name: str, sender_title: str, message_text: str) -> str | None:
    """Draft a reply to a recruiter's LinkedIn message. Returns None on failure."""
    try:
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY())
        prompt = (
            f"{_PERSONA}\n\n"
            f"Draft a short, professional reply to this LinkedIn message from {sender_name} ({sender_title}). "
            f"Be genuine, mention your interest in finance/fintech co-ops, and ask a specific follow-up question. "
            f"Under 300 characters. No fluff.\n\n"
            f"Their message: {message_text[:400]}\n\nReply:"
        )
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}]
        )
        msg = response.content[0].text.strip().strip('"')
        return msg if msg else None
    except Exception as e:
        print(f"[ai_service] generate_inbox_reply error: {e}", flush=True)
        return None
