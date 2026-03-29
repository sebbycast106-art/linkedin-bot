import pytest
import os


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_add_and_get_applications():
    from application_tracker import add_application, get_applications
    msg = add_application("j1", "BlackRock", "Finance Intern", "https://example.com")
    assert "BlackRock" in msg
    apps = get_applications()
    assert len(apps) == 1
    assert apps[0]["company"] == "BlackRock"


def test_duplicate_application():
    from application_tracker import add_application
    add_application("j1", "BlackRock", "Finance Intern")
    msg = add_application("j1", "BlackRock", "Finance Intern")
    assert "Already tracking" in msg


def test_update_status():
    from application_tracker import add_application, update_status, get_applications
    add_application("j2", "Citadel", "Quant Intern")
    msg = update_status("j2", "interview")
    assert "interview" in msg
    apps = get_applications()
    assert apps[0]["status"] == "interview"


def test_check_follow_ups_no_old_apps():
    from application_tracker import add_application, check_follow_ups
    add_application("j3", "JPMorgan", "Summer Analyst")
    reminders = check_follow_ups()
    assert reminders == []  # just applied, not 7 days old yet


def test_format_summary_empty():
    from application_tracker import format_applications_summary
    summary = format_applications_summary()
    assert "No applications" in summary


def test_add_application_with_seen_status():
    from application_tracker import add_application, get_applications
    add_application("j10", "Fidelity", "Intern", status="seen")
    apps = get_applications()
    assert apps[0]["status"] == "seen"


def test_update_status_to_seen():
    from application_tracker import add_application, update_status, get_applications
    add_application("j11", "Vanguard", "Tech Intern")
    msg = update_status("j11", "seen")
    assert "seen" in msg
    apps = get_applications()
    assert apps[0]["status"] == "seen"


def test_format_summary_shows_seen_section():
    from application_tracker import add_application, format_applications_summary
    add_application("j12", "Fidelity", "Data Intern", status="seen")
    summary = format_applications_summary()
    assert "SEEN" in summary


def test_follow_ups_skips_seen_status():
    from application_tracker import add_application, check_follow_ups
    import application_tracker
    from datetime import datetime, timezone, timedelta
    add_application("j13", "T. Rowe Price", "Software Intern", status="seen")
    # Manually set applied_at to 10 days ago to simulate old entry
    import database
    state = database.load_state(application_tracker._STATE_FILE, default={"applications": []})
    for app in state["applications"]:
        if app["job_id"] == "j13":
            app["applied_at"] = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    database.save_state(application_tracker._STATE_FILE, state)
    reminders = check_follow_ups()
    assert reminders == []
