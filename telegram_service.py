import datetime
import html
import requests
import config


# ── Time helper ───────────────────────────────────────────────────────────────

def _et_now() -> str:
    try:
        from zoneinfo import ZoneInfo
        now = datetime.datetime.now(ZoneInfo("America/New_York"))
    except Exception:
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4)))
    return now.strftime("%Y-%m-%d  %H:%M ET")


# ── HTML escaping helper ───────────────────────────────────────────────────────

def _esc(value) -> str:
    """Escape a value for safe embedding in a Telegram HTML-mode <pre> block."""
    return html.escape(str(value))


# ── Terminal block formatter ───────────────────────────────────────────────────

# Widest title in use: "ALUMNI CONNECTOR [err]" = 22 chars.  Use 24 so there
# is always at least one space of padding between the title and the timestamp.
_TITLE_COL = 24

def block(title: str, rows: list, note: str | None = None) -> str:
    """
    Build a monospaced <pre> block for Telegram HTML mode.

    title  — section label, e.g. "GAMES" or "JOBS [err]"
    rows   — list of (label, value) tuples, or a bare str for full-width lines,
             or None to insert a divider
    note   — optional summary line appended after a divider

    All label and value strings are HTML-escaped automatically so that
    user/external data (exception messages, URLs, job titles, …) cannot
    inject tags into the Telegram HTML payload.

    Example output:
        GAMES                   2026-03-30  08:15 ET
        ──────────────────────────────────────────────
        zip          solved          44s
        tango        solved          38s
        mini sudoku  solved          51s
        patches      solved        1m12s
        ──────────────────────────────────────────────
        4/4  complete   total 3m25s
    """
    ts  = _et_now()
    hdr = f"{title.upper():<{_TITLE_COL}}{ts}"
    w   = max(len(hdr), 34)
    div = "─" * w

    lines = [hdr, div]
    for row in rows:
        if row is None:
            lines.append(div)
        elif isinstance(row, str):
            lines.append(_esc(row))
        else:
            label, value = row
            lines.append(f"{_esc(label):<16}{_esc(value)}")

    if note is not None:
        lines.append(div)
        lines.append(_esc(note))

    return "<pre>" + "\n".join(lines) + "</pre>"


# ── Send ──────────────────────────────────────────────────────────────────────

# Telegram's hard limit for a single message is 4096 characters.
_TG_MAX = 4096

def send_telegram(text: str, parse_mode: str = "HTML") -> None:
    if len(text) > _TG_MAX:
        # Truncate safely: for HTML mode keep the closing tag intact.
        cutoff = _TG_MAX - 20
        text = text[:cutoff] + "\n…[truncated]"
    token   = config.TELEGRAM_BOT_TOKEN()
    chat_id = config.TELEGRAM_CHAT_ID()
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": parse_mode,
    }, timeout=10).raise_for_status()
