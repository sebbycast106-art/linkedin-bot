"""
run_games.py — Standalone runner for LinkedIn daily games.

Runs Zip, Tango, and Patches (the three main LinkedIn daily games available
in games_service.py) directly in-process via Playwright — no Flask required.

Usage:
    python run_games.py

Results are written to games_last_run.json and sent via Telegram.
"""
import os
import sys
import json
import datetime
import urllib.request
import urllib.parse

# ---------------------------------------------------------------------------
# Bootstrap: set DATA_DIR to a local path so database.py works without Railway
# ---------------------------------------------------------------------------
_LOCAL_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(_LOCAL_DATA_DIR, exist_ok=True)
os.environ.setdefault("DATA_DIR", _LOCAL_DATA_DIR)

# Ensure linkedin-bot is on the path so local modules resolve
_BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if _BOT_DIR not in sys.path:
    sys.path.insert(0, _BOT_DIR)


# ---------------------------------------------------------------------------
# Load Telegram config from co-op-bot/config.txt
# ---------------------------------------------------------------------------
def _load_config(path: str) -> dict:
    cfg = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    except Exception as e:
        print(f"[run_games] WARNING: could not read config from {path}: {e}", flush=True)
    return cfg


_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "co-op-bot", "config.txt"
)
_CONFIG_PATH = os.path.normpath(_CONFIG_PATH)
_cfg = _load_config(_CONFIG_PATH)

TELEGRAM_BOT_TOKEN = _cfg.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = _cfg.get("TELEGRAM_CHAT_ID", "")

# Inject into env so games_service/config.py doesn't raise for missing vars.
# (games_service.py itself doesn't call Telegram — only run_games.py does.)
os.environ.setdefault("TELEGRAM_BOT_TOKEN", TELEGRAM_BOT_TOKEN)
os.environ.setdefault("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
# Provide dummy values for vars games_service config.py may check at import time
os.environ.setdefault("LINKEDIN_EMAIL", "")
os.environ.setdefault("LINKEDIN_PASSWORD", "")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("SCHEDULER_SECRET", "")


# ---------------------------------------------------------------------------
# Telegram helper
# ---------------------------------------------------------------------------
def send_telegram(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[run_games] Telegram not configured — skipping notification", flush=True)
        return False
    try:
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }).encode("utf-8")
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[run_games] Telegram send failed: {e}", flush=True)
        return False


# ---------------------------------------------------------------------------
# Run individual games
# ---------------------------------------------------------------------------
def run_games() -> dict:
    """
    Run Zip, Tango, and Patches in-process via Playwright.
    Returns a results dict: {game_name: bool}
    """
    from playwright.sync_api import sync_playwright
    import database

    # Load LinkedIn cookies (required for games to load while logged in)
    cookies = database.load_state("linkedin_cookies.json", default=None)

    # Games to run: (display_name, game_id_in_service)
    games_to_run = [
        ("Zip",     "zip"),
        ("Tango",   "tango"),
        ("Patches", "patches"),
    ]

    # Import individual play functions
    from games_service import play_zip, play_tango, play_patches

    game_funcs = {
        "zip":     play_zip,
        "tango":   play_tango,
        "patches": play_patches,
    }

    results = {}

    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "general.useragent.override": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
                    "Gecko/20100101 Firefox/125.0"
                )
            },
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
                "Gecko/20100101 Firefox/125.0"
            ),
            viewport={"width": 1280, "height": 720},
            locale="en-US",
        )

        if cookies and isinstance(cookies, list):
            try:
                context.add_cookies(cookies)
            except Exception as e:
                print(f"[run_games] cookie load error: {e}", flush=True)

        page = context.new_page()

        # Verify LinkedIn login
        print("[run_games] verifying LinkedIn login...", flush=True)
        page.goto("https://www.linkedin.com/feed/", timeout=30000)
        page.wait_for_timeout(2000)
        if "login" in page.url or "authwall" in page.url:
            print("[run_games] not logged into LinkedIn — aborting", flush=True)
            browser.close()
            return {"error": "not_logged_in"}

        for display_name, game_id in games_to_run:
            print(f"[run_games] playing {display_name}...", flush=True)
            try:
                fn = game_funcs[game_id]
                won = fn(page)
                results[game_id] = {"name": display_name, "won": won}
                print(
                    f"[run_games] {display_name}: {'WON' if won else 'failed'}",
                    flush=True,
                )
            except Exception as e:
                print(f"[run_games] {display_name} raised exception: {e}", flush=True)
                results[game_id] = {"name": display_name, "won": False, "error": str(e)}

            try:
                page.wait_for_timeout(1500)
            except Exception:
                pass

        browser.close()

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ran_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"[run_games] starting at {ran_at}", flush=True)

    overall_success = True
    game_rows = []
    results = {}

    try:
        results = run_games()
    except Exception as e:
        print(f"[run_games] fatal error in run_games(): {e}", flush=True)
        overall_success = False
        results = {"fatal": {"name": "all games", "won": False, "error": str(e)}}

    if "error" in results:
        # Top-level error (e.g. not_logged_in)
        overall_success = False
        game_rows = [{"name": "LinkedIn login", "result": "failed", "score": None}]
    else:
        for game_id, info in results.items():
            won = info.get("won", False)
            err = info.get("error")
            if not won:
                overall_success = False
            game_rows.append({
                "name":   info.get("name", game_id),
                "result": "won" if won else "failed",
                "score":  None,  # LinkedIn doesn't expose a numeric score
                "error":  err,
            })

    # ------------------------------------------------------------------
    # Write games_last_run.json
    # ------------------------------------------------------------------
    output = {
        "ran_at_iso": ran_at,
        "games":      game_rows,
        "success":    overall_success,
    }
    output_path = os.path.join(_BOT_DIR, "games_last_run.json")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"[run_games] results written to {output_path}", flush=True)
    except Exception as e:
        print(f"[run_games] could not write results file: {e}", flush=True)

    # ------------------------------------------------------------------
    # Send Telegram notification
    # ------------------------------------------------------------------
    status_icon = "✅" if overall_success else "⚠️"
    lines = [f"{status_icon} <b>LinkedIn Daily Games</b> — {ran_at[:10]}"]
    for row in game_rows:
        icon = "✅" if row["result"] == "won" else "❌"
        line = f"  {icon} {row['name']}: {row['result']}"
        if row.get("error"):
            line += f" ({row['error'][:80]})"
        lines.append(line)

    msg = "\n".join(lines)
    print(f"[run_games] sending Telegram: {msg!r}", flush=True)
    send_telegram(msg)

    print(f"[run_games] done. success={overall_success}", flush=True)
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
