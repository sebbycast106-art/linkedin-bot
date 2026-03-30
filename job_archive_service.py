"""
job_archive_service.py — Archive job descriptions from Easy Apply submissions.

Saves full job description text so it can be referenced later for interview prep or follow-ups.
State file: job_archive_state.json

Public interface:
    archive_description(job_id, title, company, url, description) -> None
    get_archived_description(job_id) -> str | None
    get_all_archived() -> list[dict]
"""
import database
from datetime import datetime, timezone

_STATE_FILE = "job_archive_state.json"
_MAX_DESC_LENGTH = 3000
_MAX_ENTRIES = 200


def _load():
    return database.load_state(_STATE_FILE, default={"archived": []})


def _save(state):
    database.save_state(_STATE_FILE, state)


def archive_description(job_id: str, title: str, company: str, url: str, description: str):
    """Save a job description. Deduplicates by job_id, caps at 200 entries."""
    state = _load()
    archived = state.get("archived", [])

    # Dedup by job_id
    for entry in archived:
        if entry.get("job_id") == job_id:
            return

    archived.append({
        "job_id": job_id,
        "title": title,
        "company": company,
        "url": url,
        "description": description[:_MAX_DESC_LENGTH],
        "archived_at": datetime.now(timezone.utc).isoformat(),
    })

    # Cap at 200 entries — keep most recent
    if len(archived) > _MAX_ENTRIES:
        archived.sort(key=lambda x: x.get("archived_at", ""), reverse=True)
        archived = archived[:_MAX_ENTRIES]

    state["archived"] = archived
    _save(state)


def get_archived_description(job_id: str):
    """Return description text for a job_id, or None if not found."""
    state = _load()
    for entry in state.get("archived", []):
        if entry.get("job_id") == job_id:
            return entry.get("description")
    return None


def get_all_archived() -> list:
    """Return all archived entries sorted by archived_at descending."""
    state = _load()
    archived = state.get("archived", [])
    archived.sort(key=lambda x: x.get("archived_at", ""), reverse=True)
    return archived
