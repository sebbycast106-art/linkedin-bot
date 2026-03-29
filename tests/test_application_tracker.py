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
