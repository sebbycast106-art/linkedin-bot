import pytest
import os

@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("LINKEDIN_EMAIL", "test@test.com")
    monkeypatch.setenv("LINKEDIN_PASSWORD", "testpass")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:test")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "999")
    monkeypatch.setenv("SCHEDULER_SECRET", "test-secret")
    monkeypatch.setenv("DATA_DIR", "/tmp/linkedin-test")
