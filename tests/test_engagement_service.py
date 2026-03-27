from unittest.mock import patch
import engagement_service

def test_can_act_returns_true_under_limit():
    state = {"comments": 0, "likes": 0, "date": "2026-03-27"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        assert engagement_service.can_act("comments", state, limit=25) is True

def test_can_act_returns_false_at_limit():
    state = {"comments": 25, "likes": 0, "date": "2026-03-27"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        assert engagement_service.can_act("comments", state, limit=25) is False

def test_can_act_resets_on_new_day():
    state = {"comments": 25, "likes": 50, "date": "2026-03-26"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        assert engagement_service.can_act("comments", state, limit=25) is True

def test_increment_action():
    state = {"comments": 5, "likes": 3, "date": "2026-03-27"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        result = engagement_service.increment_action("comments", state)
    assert result["comments"] == 6

def test_increment_action_resets_on_new_day():
    state = {"comments": 20, "likes": 10, "date": "2026-03-26"}
    with patch("engagement_service._today", return_value="2026-03-27"):
        result = engagement_service.increment_action("comments", state)
    assert result["comments"] == 1
    assert result["date"] == "2026-03-27"
