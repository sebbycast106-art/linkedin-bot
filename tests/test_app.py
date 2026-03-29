import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def client():
    import app as application
    application.app.config["TESTING"] = True
    with application.app.test_client() as c:
        yield c

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["status"] == "ok"

def test_job_scraper_rejects_bad_secret(client):
    res = client.post("/internal/run-job-scraper?secret=wrong")
    assert res.status_code == 403

def test_engagement_rejects_bad_secret(client):
    res = client.post("/internal/run-engagement?secret=wrong")
    assert res.status_code == 403

def test_connector_rejects_bad_secret(client):
    res = client.post("/internal/run-connector?secret=wrong")
    assert res.status_code == 403

def test_job_scraper_returns_ok(client):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-job-scraper?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"

def test_engagement_returns_ok(client):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-engagement?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"

def test_connector_returns_ok(client):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-connector?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"

def test_linkedin_verify_requires_code(client):
    res = client.post("/internal/linkedin-verify?secret=test-secret", json={})
    assert res.status_code == 400

def test_linkedin_reset(client):
    with patch("database.save_state"):
        res = client.post("/internal/linkedin-reset?secret=test-secret")
    assert res.json["status"] == "ok"


def test_track_application(client):
    resp = client.post(
        "/internal/track-application?secret=test-secret",
        json={"job_id": "abc123", "company": "Goldman Sachs", "title": "Analyst Intern", "url": "https://linkedin.com/jobs/123"}
    )
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


def test_track_application_missing_fields(client):
    resp = client.post("/internal/track-application?secret=test-secret", json={"job_id": "x"})
    assert resp.status_code == 400


def test_list_applications(client):
    resp = client.get("/internal/applications?secret=test-secret")
    assert resp.status_code == 200
    assert "applications" in resp.json


def test_check_follow_ups_endpoint(client):
    resp = client.post("/internal/check-follow-ups?secret=test-secret")
    assert resp.json["status"] == "ok"


def test_run_recruiter_rejects_bad_secret(client):
    res = client.post("/internal/run-recruiter?secret=wrong")
    assert res.status_code == 403


def test_run_recruiter_returns_ok(client):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-recruiter?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"


def test_run_recruiter_followup_rejects_bad_secret(client):
    res = client.post("/internal/run-recruiter-followup?secret=wrong")
    assert res.status_code == 403


def test_run_recruiter_followup_returns_ok(client):
    with patch("app.threading.Thread") as mock_thread:
        mock_thread.return_value.start = MagicMock()
        res = client.post("/internal/run-recruiter-followup?secret=test-secret")
    assert res.status_code == 200
    assert res.json["status"] == "ok"
