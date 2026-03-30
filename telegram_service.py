import datetime
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


# ── Terminal block formatter ───────────────────────────────────────────────────

def block(title: str, rows: list, note: str | None = None) -> str:
    """
    Build a monospaced <pre> block for Telegram HTML mode.

    title  — section label, e.g. "GAMES" or "JOBS [err]"
    rows   — list of (label, value) tuples, or a bare str for full-width lines,
             or None to insert a divider
    note   — optional summary line appended after a divider

    Example output:
        GAMES        2026-03-30  08:15 ET
        ────────────────────────────────
        zip          solved          44s
        tango        solved          38s
        mini sudoku  solved          51s
        patches      solved        1m12s
        ────────────────────────────────
        4/4  complete   total 3m25s
    """
    ts  = _et_now()
    hdr = f"{title.upper():<14}{ts}"
    w   = max(len(hdr), 34)
    div = "─" * w

    lines = [hdr, div]
    for row in rows:
        if row is None:
            lines.append(div)
        elif isinstance(row, str):
            lines.append(row)
        else:
            label, value = row
            lines.append(f"{str(label):<16}{value}")

    if note is not None:
        lines.append(div)
        lines.append(note)

    return "<pre>" + "\n".join(lines) + "</pre>"


# ── Send ──────────────────────────────────────────────────────────────────────

def send_telegram(text: str, parse_mode: str = "HTML") -> None:
    token   = config.TELEGRAM_BOT_TOKEN()
    chat_id = config.TELEGRAM_CHAT_ID()
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, json={
        "chat_id":    chat_id,
        "text":       text,
        "parse_mode": parse_mode,
    }, timeout=10).raise_for_status()
