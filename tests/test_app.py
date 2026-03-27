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
