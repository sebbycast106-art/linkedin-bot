import pytest
from unittest.mock import patch, MagicMock


def test_default_profile():
    from skill_match_service import get_skill_profile
    with patch("skill_match_service.database") as mock_db:
        mock_db.load_state.return_value = {
            "skills": [],
            "target_roles": [],
            "updated_at": "",
        }
        profile = get_skill_profile()
        # Falls back to default when skills is empty
        assert len(profile["skills"]) == 8
        assert "python" in profile["skills"]


def test_get_skill_profile_returns_saved():
    from skill_match_service import get_skill_profile
    saved = {
        "skills": ["python", "sql"],
        "target_roles": ["data analyst"],
        "updated_at": "2026-01-01",
    }
    with patch("skill_match_service.database") as mock_db:
        mock_db.load_state.return_value = saved
        profile = get_skill_profile()
        assert profile["skills"] == ["python", "sql"]
        assert profile["target_roles"] == ["data analyst"]


def test_update_skill_profile_skills():
    from skill_match_service import update_skill_profile
    with patch("skill_match_service.database") as mock_db:
        mock_db.load_state.return_value = {
            "skills": ["python"],
            "target_roles": ["analyst"],
            "updated_at": "",
        }
        result = update_skill_profile(skills=["python", "sql", "excel"])
        assert "3 skills" in result
        mock_db.save_state.assert_called_once()
        saved_data = mock_db.save_state.call_args[0][1]
        assert saved_data["skills"] == ["python", "sql", "excel"]


def test_update_skill_profile_target_roles():
    from skill_match_service import update_skill_profile
    with patch("skill_match_service.database") as mock_db:
        mock_db.load_state.return_value = {
            "skills": ["python"],
            "target_roles": ["analyst"],
            "updated_at": "",
        }
        result = update_skill_profile(target_roles=["quant", "trader"])
        assert "2 target roles" in result


def test_score_job_match_with_mocked_claude():
    from skill_match_service import score_job_match
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="85")]

    with patch("skill_match_service.database") as mock_db, \
         patch("skill_match_service.anthropic") as mock_anthropic:
        mock_db.load_state.return_value = {
            "skills": ["python", "data analysis"],
            "target_roles": ["data analyst"],
            "updated_at": "",
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        score = score_job_match("Data Analyst", "Goldman Sachs", "Python data analysis role")
        assert score == 85


def test_score_job_match_clamps_to_range():
    from skill_match_service import score_job_match
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="150")]

    with patch("skill_match_service.database") as mock_db, \
         patch("skill_match_service.anthropic") as mock_anthropic:
        mock_db.load_state.return_value = {
            "skills": ["python"],
            "target_roles": ["analyst"],
            "updated_at": "",
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        score = score_job_match("Test", "Test", "Test")
        assert score == 100


def test_score_job_match_returns_50_on_error():
    from skill_match_service import score_job_match
    with patch("skill_match_service.database") as mock_db, \
         patch("skill_match_service.anthropic") as mock_anthropic:
        mock_db.load_state.return_value = {
            "skills": ["python"],
            "target_roles": ["analyst"],
            "updated_at": "",
        }
        mock_anthropic.Anthropic.side_effect = Exception("API error")

        score = score_job_match("Test", "Test", "Test")
        assert score == 50


def test_score_job_match_non_numeric_response():
    from skill_match_service import score_job_match
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="This is a great match!")]

    with patch("skill_match_service.database") as mock_db, \
         patch("skill_match_service.anthropic") as mock_anthropic:
        mock_db.load_state.return_value = {
            "skills": ["python"],
            "target_roles": ["analyst"],
            "updated_at": "",
        }
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        score = score_job_match("Test", "Test", "Test")
        assert score == 50
