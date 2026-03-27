from unittest.mock import patch, MagicMock
import ai_service

def test_generate_comment_returns_string():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Interesting perspective on the role of AI in finance.")]
    mock_client.messages.create.return_value = mock_response

    with patch("ai_service.anthropic.Anthropic", return_value=mock_client):
        result = ai_service.generate_comment(
            post_text="The future of fintech is decentralized.",
            author_name="Jane Smith"
        )
    assert isinstance(result, str)
    assert len(result) > 5

def test_generate_comment_returns_none_on_error():
    with patch("ai_service.anthropic.Anthropic", side_effect=Exception("API error")):
        result = ai_service.generate_comment("Some post", "Author")
    assert result is None

def test_generate_connection_message_returns_string():
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hi! I'm a Northeastern student interested in your work at Goldman.")]
    mock_client.messages.create.return_value = mock_response

    with patch("ai_service.anthropic.Anthropic", return_value=mock_client):
        result = ai_service.generate_connection_message("John", "Analyst", "Goldman Sachs")
    assert isinstance(result, str)
    assert len(result) <= 299

def test_generate_connection_message_returns_none_on_error():
    with patch("ai_service.anthropic.Anthropic", side_effect=Exception("err")):
        result = ai_service.generate_connection_message("John", "Analyst", "Goldman")
    assert result is None
