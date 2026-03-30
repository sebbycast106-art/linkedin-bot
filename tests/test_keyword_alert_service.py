import pytest
from unittest.mock import patch, MagicMock


def _make_state(keywords=None, alerted_job_ids=None):
    return {
        "keywords": keywords if keywords is not None else ["analyst", "trading"],
        "alerted_job_ids": alerted_job_ids if alerted_job_ids is not None else [],
    }


def _make_job(job_id, company, title):
    return {"job_id": job_id, "company": company, "title": title, "url": "", "applied_at": "", "status": "seen"}


@patch("keyword_alert_service.database")
def test_get_keywords_default(mock_db):
    mock_db.load_state.return_value = {}
    from keyword_alert_service import get_keywords
    keywords = get_keywords()
    assert "analyst" in keywords
    assert "quantitative" in keywords


@patch("keyword_alert_service.database")
def test_add_keyword(mock_db):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"])
    from keyword_alert_service import add_keyword
    result = add_keyword("quant")
    assert "Added" in result
    mock_db.save_state.assert_called_once()
    saved = mock_db.save_state.call_args[0][1]
    assert "quant" in saved["keywords"]


@patch("keyword_alert_service.database")
def test_add_duplicate_keyword(mock_db):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"])
    from keyword_alert_service import add_keyword
    result = add_keyword("analyst")
    assert "already exists" in result


@patch("keyword_alert_service.database")
def test_remove_keyword(mock_db):
    mock_db.load_state.return_value = _make_state(keywords=["analyst", "trading"])
    from keyword_alert_service import remove_keyword
    result = remove_keyword("analyst")
    assert "Removed" in result
    saved = mock_db.save_state.call_args[0][1]
    assert "analyst" not in saved["keywords"]


@patch("keyword_alert_service.database")
def test_remove_nonexistent_keyword(mock_db):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"])
    from keyword_alert_service import remove_keyword
    result = remove_keyword("nonexistent")
    assert "not found" in result


@patch("keyword_alert_service.database")
def test_check_keywords_matches(mock_db):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"])
    jobs = [
        _make_job("j1", "Goldman Sachs", "Quantitative Analyst"),
        _make_job("j2", "Google", "Software Engineer"),
    ]
    from keyword_alert_service import check_keywords
    matched = check_keywords(jobs)
    assert len(matched) == 1
    assert matched[0]["job_id"] == "j1"


@patch("keyword_alert_service.database")
def test_check_keywords_skips_already_alerted(mock_db):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"], alerted_job_ids=["j1"])
    jobs = [_make_job("j1", "Goldman Sachs", "Analyst")]
    from keyword_alert_service import check_keywords
    matched = check_keywords(jobs)
    assert len(matched) == 0


@patch("keyword_alert_service.send_telegram")
@patch("keyword_alert_service.application_tracker")
@patch("keyword_alert_service.database")
def test_run_keyword_alerts_sends_telegram(mock_db, mock_tracker, mock_tg):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"])
    mock_tracker.get_applications.return_value = [
        _make_job("j1", "Goldman Sachs", "Analyst Intern"),
    ]
    from keyword_alert_service import run_keyword_alerts
    result = run_keyword_alerts()
    assert result["matched"] == 1
    assert result["alerted"] == 1
    mock_tg.assert_called_once()
    mock_db.save_state.assert_called()


@patch("keyword_alert_service.send_telegram")
@patch("keyword_alert_service.application_tracker")
@patch("keyword_alert_service.database")
def test_run_keyword_alerts_no_matches(mock_db, mock_tracker, mock_tg):
    mock_db.load_state.return_value = _make_state(keywords=["analyst"])
    mock_tracker.get_applications.return_value = [
        _make_job("j1", "Google", "Software Engineer"),
    ]
    from keyword_alert_service import run_keyword_alerts
    result = run_keyword_alerts()
    assert result["matched"] == 0
    assert result["alerted"] == 0
    mock_tg.assert_not_called()


@patch("keyword_alert_service.database")
def test_alerted_ids_capped(mock_db):
    # Create state with max alerted IDs
    mock_db.load_state.return_value = _make_state(
        keywords=["analyst"],
        alerted_job_ids=[f"id_{i}" for i in range(2001)]
    )
    from keyword_alert_service import _save
    state = mock_db.load_state.return_value
    _save(state)
    saved = mock_db.save_state.call_args[0][1]
    assert len(saved["alerted_job_ids"]) <= 2000
