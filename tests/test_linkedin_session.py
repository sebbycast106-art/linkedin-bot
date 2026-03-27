from unittest.mock import patch, MagicMock
import linkedin_session

def test_random_delay_is_in_range():
    import time
    start = time.time()
    linkedin_session.random_delay(0.05, 0.1)
    elapsed = time.time() - start
    assert 0.05 <= elapsed <= 0.5

def test_linkedin_session_enters_and_exits(monkeypatch):
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_context.cookies.return_value = []
    mock_page = MagicMock()
    mock_page.url = "https://www.linkedin.com/feed/"
    mock_context.new_page.return_value = mock_page
    mock_browser.new_context.return_value = mock_context
    mock_pw.chromium.launch.return_value = mock_browser
    mock_sync_pw = MagicMock()
    mock_sync_pw.__enter__ = MagicMock(return_value=mock_pw)
    mock_sync_pw.__exit__ = MagicMock(return_value=False)

    with patch("linkedin_session.sync_playwright", return_value=mock_sync_pw), \
         patch("linkedin_session.database.load_state", return_value=[]), \
         patch("linkedin_session.database.save_state"), \
         patch("linkedin_session.random_delay"):
        with linkedin_session.LinkedInSession() as session:
            assert session is not None
