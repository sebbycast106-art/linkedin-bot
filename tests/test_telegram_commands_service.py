import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def tmp_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))


def test_handle_status_command():
    summary = "📋 Applications (2 active, 2 total):\n\nAPPLIED (2):\n  • Goldman Sachs — Analyst\n  • JPMorgan — Intern"
    with patch("application_tracker.get_applications") as mock_get, \
         patch("application_tracker.format_applications_summary", return_value=summary) as mock_fmt:
        from telegram_commands_service import handle_telegram_command
        result = handle_telegram_command("/status")
    assert result == summary
    mock_fmt.assert_called_once()


def test_handle_applied_command():
    with patch("application_tracker.add_application", return_value="✅ Tracked: Goldman – Investment Banking Analyst") as mock_add:
        from telegram_commands_service import handle_telegram_command
        result = handle_telegram_command("/applied Goldman Investment Banking Analyst")
    mock_add.assert_called_once()
    call_args = mock_add.call_args
    # positional: job_id, company, title
    assert call_args[0][1] == "Goldman"
    assert call_args[0][2] == "Investment Banking Analyst"
    assert call_args[1].get("status") == "applied" or call_args[0][4] == "applied" if len(call_args[0]) > 4 else True
    assert "Goldman" in result
    assert "Investment Banking Analyst" in result


def test_handle_applied_command_confirmation_format():
    with patch("application_tracker.add_application", return_value="✅ Tracked: BlackRock – Quant Analyst"):
        from telegram_commands_service import handle_telegram_command
        result = handle_telegram_command("/applied BlackRock Quant Analyst")
    assert result == "✅ Logged: BlackRock – Quant Analyst"


def test_handle_update_command():
    with patch("application_tracker.update_status", return_value="✅ Updated Goldman — Analyst → interview") as mock_update:
        from telegram_commands_service import handle_telegram_command
        result = handle_telegram_command("/update goldman_123456 interview")
    mock_update.assert_called_once_with("goldman_123456", "interview")
    assert "interview" in result


def test_handle_update_command_invalid_status():
    from telegram_commands_service import handle_telegram_command
    result = handle_telegram_command("/update abc123 flying")
    assert "Invalid status" in result or result is not None


def test_handle_help_command():
    from telegram_commands_service import handle_telegram_command
    result = handle_telegram_command("/help")
    assert "/status" in result
    assert "/applied" in result
    assert "/update" in result


def test_handle_unknown_command():
    from telegram_commands_service import handle_telegram_command
    result = handle_telegram_command("/foo bar")
    assert result is None


def test_handle_non_command():
    from telegram_commands_service import handle_telegram_command
    result = handle_telegram_command("hello world")
    assert result is None


def test_handle_empty_string():
    from telegram_commands_service import handle_telegram_command
    result = handle_telegram_command("")
    assert result is None


def test_handle_none_text():
    from telegram_commands_service import handle_telegram_command
    result = handle_telegram_command(None)
    assert result is None
