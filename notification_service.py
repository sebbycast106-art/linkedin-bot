"""
notification_service.py — Structured notification buffering and batched delivery.

Public interface:
    send_or_buffer(category, message, priority="normal", immediate=False)
    buffer_notification(category, message, priority="normal")
    flush_notifications() -> dict  # {"sent": N}
"""
from datetime import datetime, timezone
import database
from telegram_service import send_telegram

_STATE_FILE = "notification_buffer_state.json"
_VALID_CATEGORIES = {"jobs", "networking", "applications", "system"}
_BUFFER_CAP = 50

_CATEGORY_HEADERS = {
    "jobs": "💼 Jobs",
    "networking": "🤝 Networking",
    "applications": "📋 Applications",
    "system": "⚙️ System",
}


def _load() -> dict:
    state = database.load_state(_STATE_FILE, default={})
    if "buffer" not in state:
        state["buffer"] = []
    if "last_flush" not in state:
        state["last_flush"] = ""
    return state


def _save(state: dict):
    database.save_state(_STATE_FILE, state)


def buffer_notification(category: str, message: str, priority: str = "normal"):
    """Add a notification to the buffer. Auto-flushes if buffer exceeds cap."""
    if category not in _VALID_CATEGORIES:
        category = "system"

    state = _load()
    state["buffer"].append({
        "category": category,
        "message": message,
        "priority": priority,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    _save(state)

    # Auto-flush if buffer exceeds cap
    if len(state["buffer"]) >= _BUFFER_CAP:
        flush_notifications()


def send_or_buffer(category: str, message: str, priority: str = "normal", immediate: bool = False):
    """Send immediately if high priority or immediate=True, otherwise buffer."""
    if priority == "high" or immediate:
        send_telegram(message)
    else:
        buffer_notification(category, message, priority)


def flush_notifications() -> dict:
    """Group buffered notifications by category, send as single message, clear buffer."""
    state = _load()
    buffer = state["buffer"]

    if not buffer:
        return {"sent": 0}

    # Group by category
    grouped = {}
    for item in buffer:
        cat = item["category"]
        grouped.setdefault(cat, []).append(item["message"])

    # Build message with category headers
    lines = ["📬 Notification Digest:"]
    for cat in ["jobs", "networking", "applications", "system"]:
        if cat in grouped:
            header = _CATEGORY_HEADERS.get(cat, cat.title())
            lines.append(f"\n{header} ({len(grouped[cat])}):")
            for msg in grouped[cat]:
                lines.append(f"  • {msg}")

    send_telegram("\n".join(lines))

    count = len(buffer)
    state["buffer"] = []
    state["last_flush"] = datetime.now(timezone.utc).isoformat()
    _save(state)

    return {"sent": count}
