"""
warmth_scorer_service.py — Track connection engagement signals and compute warmth scores.

Public interface:
    record_signal(profile_id, name, signal) -> None
    get_warmth_scores(min_score=0) -> list[dict]
    get_warmth(profile_id) -> dict | None
"""
import database
from datetime import datetime, timezone

_STATE_FILE = "warmth_scores_state.json"
_MAX_ENTRIES = 2000

_SIGNAL_VALUES = {
    "connection_accepted": 20,
    "messaged_us": 40,
    "viewed_profile": 15,
    "we_messaged": 10,
}


def _load_state() -> dict:
    return database.load_state(_STATE_FILE, default={"scores": {}})


def _save_state(state: dict) -> None:
    database.save_state(_STATE_FILE, state)


def record_signal(profile_id: str, name: str, signal: str) -> None:
    """Record an engagement signal for a connection.

    Adds points based on signal type. Caps total entries at _MAX_ENTRIES.
    """
    if signal not in _SIGNAL_VALUES:
        print(f"[warmth_scorer] unknown signal: {signal}", flush=True)
        return

    state = _load_state()
    scores = state.get("scores", {})

    entry = scores.get(profile_id, {
        "name": name,
        "score": 0,
        "signals": {},
        "last_updated": "",
    })

    entry["name"] = name or entry.get("name", "")
    entry["score"] = entry.get("score", 0) + _SIGNAL_VALUES[signal]
    signals = entry.get("signals", {})
    signals[signal] = signals.get(signal, 0) + 1
    entry["signals"] = signals
    entry["last_updated"] = datetime.now(timezone.utc).isoformat()

    scores[profile_id] = entry

    # Cap at _MAX_ENTRIES — keep highest scores
    if len(scores) > _MAX_ENTRIES:
        sorted_ids = sorted(scores, key=lambda pid: scores[pid].get("score", 0), reverse=True)
        scores = {pid: scores[pid] for pid in sorted_ids[:_MAX_ENTRIES]}

    state["scores"] = scores
    _save_state(state)


def get_warmth_scores(min_score: int = 0) -> list:
    """Return all tracked connections sorted by warmth score (descending).

    Each item: {"profile_id": str, "name": str, "score": int, "signals": dict, "last_updated": str}
    """
    state = _load_state()
    scores = state.get("scores", {})

    result = []
    for profile_id, data in scores.items():
        score = data.get("score", 0)
        if score >= min_score:
            result.append({
                "profile_id": profile_id,
                "name": data.get("name", ""),
                "score": score,
                "signals": data.get("signals", {}),
                "last_updated": data.get("last_updated", ""),
            })

    result.sort(key=lambda x: x["score"], reverse=True)
    return result


def get_warmth(profile_id: str) -> dict | None:
    """Return warmth data for a single connection, or None if not tracked."""
    state = _load_state()
    scores = state.get("scores", {})
    data = scores.get(profile_id)
    if data is None:
        return None
    return {
        "profile_id": profile_id,
        "name": data.get("name", ""),
        "score": data.get("score", 0),
        "signals": data.get("signals", {}),
        "last_updated": data.get("last_updated", ""),
    }
