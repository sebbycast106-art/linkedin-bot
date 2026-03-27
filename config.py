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
