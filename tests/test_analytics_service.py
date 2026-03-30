import pytest
import json
import os
from unittest.mock import patch


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    return tmp_path


def _write_state(tmp_path, filename, data):
    with open(os.path.join(str(tmp_path), filename), "w") as f:
        json.dump(data, f)


def test_returns_all_expected_keys(tmp_data_dir):
    from analytics_service import compute_analytics
    result = compute_analytics()
    assert "acceptance_rate" in result
    assert "accepted" in result
    assert "declined" in result
    assert "funnel" in result
    assert "conversion_rates" in result
    assert "top_companies" in result
    assert "total_connections" in result
    assert "total_easy_applies" in result
    assert "total_recruiter_outreaches" in result
    assert "recruiter_response_rate" in result


def test_acceptance_rate_math(tmp_data_dir):
    _write_state(tmp_data_dir, "connection_tracker_state.json", {
        "accepted_count": 3,
        "declined_count": 7,
        "pending": [],
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    assert result["acceptance_rate"] == 0.3
    assert result["accepted"] == 3
    assert result["declined"] == 7


def test_zero_division_acceptance_rate(tmp_data_dir):
    _write_state(tmp_data_dir, "connection_tracker_state.json", {
        "accepted_count": 0,
        "declined_count": 0,
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    assert result["acceptance_rate"] == 0.0


def test_zero_division_conversion_rates(tmp_data_dir):
    _write_state(tmp_data_dir, "application_tracker_state.json", {
        "applications": [],
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    rates = result["conversion_rates"]
    assert rates["seen_to_applied"] == 0.0
    assert rates["applied_to_responded"] == 0.0
    assert rates["responded_to_interview"] == 0.0
    assert rates["interview_to_offer"] == 0.0


def test_funnel_counts(tmp_data_dir):
    _write_state(tmp_data_dir, "application_tracker_state.json", {
        "applications": [
            {"job_id": "1", "company": "Goldman", "title": "Analyst", "status": "seen"},
            {"job_id": "2", "company": "Goldman", "title": "Intern", "status": "seen"},
            {"job_id": "3", "company": "JPMorgan", "title": "Analyst", "status": "applied"},
            {"job_id": "4", "company": "BlackRock", "title": "Quant", "status": "responded"},
            {"job_id": "5", "company": "Citadel", "title": "Dev", "status": "interview"},
            {"job_id": "6", "company": "Stripe", "title": "SWE", "status": "offer"},
            {"job_id": "7", "company": "Fidelity", "title": "Analyst", "status": "rejected"},
        ],
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    funnel = result["funnel"]
    assert funnel["seen"] == 2
    assert funnel["applied"] == 1
    assert funnel["responded"] == 1
    assert funnel["interview"] == 1
    assert funnel["offer"] == 1
    assert funnel["rejected"] == 1


def test_conversion_rates_with_data(tmp_data_dir):
    _write_state(tmp_data_dir, "application_tracker_state.json", {
        "applications": [
            {"job_id": "1", "company": "A", "title": "X", "status": "seen"},
            {"job_id": "2", "company": "A", "title": "X", "status": "seen"},
            {"job_id": "3", "company": "B", "title": "X", "status": "seen"},
            {"job_id": "4", "company": "B", "title": "X", "status": "seen"},
            {"job_id": "5", "company": "C", "title": "X", "status": "applied"},
            {"job_id": "6", "company": "C", "title": "X", "status": "applied"},
            {"job_id": "7", "company": "D", "title": "X", "status": "responded"},
            {"job_id": "8", "company": "D", "title": "X", "status": "interview"},
        ],
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    rates = result["conversion_rates"]
    # 2 applied / 4 seen = 0.5
    assert rates["seen_to_applied"] == 0.5
    # 1 responded / 2 applied = 0.5
    assert rates["applied_to_responded"] == 0.5
    # 1 interview / 1 responded = 1.0
    assert rates["responded_to_interview"] == 1.0
    # 0 offer / 1 interview = 0.0
    assert rates["interview_to_offer"] == 0.0


def test_top_companies(tmp_data_dir):
    _write_state(tmp_data_dir, "application_tracker_state.json", {
        "applications": [
            {"job_id": "1", "company": "Goldman", "title": "A", "status": "seen"},
            {"job_id": "2", "company": "Goldman", "title": "B", "status": "applied"},
            {"job_id": "3", "company": "Goldman", "title": "C", "status": "seen"},
            {"job_id": "4", "company": "JPMorgan", "title": "D", "status": "seen"},
            {"job_id": "5", "company": "JPMorgan", "title": "E", "status": "applied"},
            {"job_id": "6", "company": "Citadel", "title": "F", "status": "seen"},
        ],
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    top = result["top_companies"]
    assert top[0] == ("Goldman", 3)
    assert top[1] == ("JPMorgan", 2)


def test_empty_state(tmp_data_dir):
    from analytics_service import compute_analytics
    result = compute_analytics()
    assert result["acceptance_rate"] == 0.0
    assert result["funnel"]["seen"] == 0
    assert result["funnel"]["applied"] == 0
    assert result["total_connections"] == 0
    assert result["total_easy_applies"] == 0
    assert result["total_recruiter_outreaches"] == 0
    assert result["recruiter_response_rate"] == 0.0
    assert result["top_companies"] == []


def test_recruiter_metrics(tmp_data_dir):
    _write_state(tmp_data_dir, "recruiter_state.json", {
        "date": "2026-03-29",
        "sent_today": 5,
        "pending_followup": [
            {"name": "Alice", "profile_url": "https://linkedin.com/in/alice"},
            {"name": "Bob", "profile_url": "https://linkedin.com/in/bob"},
        ],
        "messaged_ids": ["charlie_id", "dave_id", "eve_id"],
    })
    from analytics_service import compute_analytics
    result = compute_analytics()
    assert result["total_recruiter_outreaches"] == 5  # 2 pending + 3 messaged
    assert result["recruiter_response_rate"] == 0.6  # 3/5
