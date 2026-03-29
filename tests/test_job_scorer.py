import pytest
from unittest.mock import patch, MagicMock
import job_scorer
import job_scraper


# ---------------------------------------------------------------------------
# score_job tests
# ---------------------------------------------------------------------------

def _make_response(text: str):
    """Build a minimal mock Anthropic messages response."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


def test_score_job_returns_integer():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("8")
    with patch("job_scorer.anthropic.Anthropic", return_value=mock_client):
        result = job_scorer.score_job("Finance Intern", "BlackRock")
    assert result == 8


def test_score_job_returns_5_on_error():
    with patch("job_scorer.anthropic.Anthropic", side_effect=Exception("API down")):
        result = job_scorer.score_job("Some Job", "Some Company")
    assert result == 5


def test_score_job_returns_5_on_bad_response():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_response("excellent")
    with patch("job_scorer.anthropic.Anthropic", return_value=mock_client):
        result = job_scorer.score_job("Some Job", "Some Company")
    assert result == 5


# ---------------------------------------------------------------------------
# filter_and_score_jobs tests
# ---------------------------------------------------------------------------

_SAMPLE_JOBS = [
    {"title": "Finance Co-op", "company": "Fidelity", "location": "Boston", "url": "https://example.com/1", "job_id": "1"},
    {"title": "Investment Banking Intern", "company": "Goldman Sachs", "location": "NYC", "url": "https://example.com/2", "job_id": "2"},
    {"title": "Marketing Intern", "company": "Random Inc", "location": "Remote", "url": "https://example.com/3", "job_id": "3"},
]


def test_filter_keeps_high_scores():
    with patch("job_scorer.score_job", return_value=8):
        result = job_scorer.filter_and_score_jobs(_SAMPLE_JOBS, min_score=6)
    assert len(result) == len(_SAMPLE_JOBS)


def test_filter_removes_low_scores():
    with patch("job_scorer.score_job", return_value=3):
        result = job_scorer.filter_and_score_jobs(_SAMPLE_JOBS, min_score=6)
    assert result == []


def test_filter_adds_score_to_job():
    with patch("job_scorer.score_job", return_value=9):
        result = job_scorer.filter_and_score_jobs([_SAMPLE_JOBS[0]], min_score=6)
    assert len(result) == 1
    assert result[0]["score"] == 9


def test_filter_sorts_by_score():
    scores = [7, 9, 6]
    call_count = {"n": 0}

    def side_effect(title, company):
        s = scores[call_count["n"]]
        call_count["n"] += 1
        return s

    with patch("job_scorer.score_job", side_effect=side_effect):
        result = job_scorer.filter_and_score_jobs(_SAMPLE_JOBS, min_score=6)

    assert [j["score"] for j in result] == [9, 7, 6]


# ---------------------------------------------------------------------------
# format_job_message tests (in job_scraper)
# ---------------------------------------------------------------------------

def test_format_job_message_with_score():
    job = {
        "title": "Finance Co-op",
        "company": "Fidelity",
        "location": "Boston, MA",
        "url": "https://www.linkedin.com/jobs/view/123",
        "job_id": "123",
        "score": 9,
    }
    msg = job_scraper.format_job_message(job)
    assert "⭐9/10" in msg


def test_format_job_message_without_score():
    job = {
        "title": "Finance Co-op",
        "company": "Fidelity",
        "location": "Boston, MA",
        "url": "https://www.linkedin.com/jobs/view/123",
        "job_id": "123",
    }
    msg = job_scraper.format_job_message(job)
    assert "⭐" not in msg
