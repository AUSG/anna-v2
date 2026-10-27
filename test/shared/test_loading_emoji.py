import unittest
from unittest.mock import MagicMock

from shared.loading_emoji import EMOJI_NAME, with_loading_emoji
from test.fixtures.runtime import fake_slack


class TestWithLoadingEmoji(unittest.TestCase):
    def test_adds_before_action_and_removes_after(self):
        slack = fake_slack()

        def action():
            slack.add_reaction.assert_called_once_with("C1", "123.456", EMOJI_NAME)
            slack.remove_reaction.assert_not_called()
            return "done"

        assert with_loading_emoji(slack, "C1", "123.456", action) == "done"

        slack.remove_reaction.assert_called_once_with("C1", "123.456", EMOJI_NAME)

    def test_removes_even_when_action_raises(self):
        slack = fake_slack()
        action = MagicMock(side_effect=RuntimeError("boom"))

        with self.assertRaises(RuntimeError):
            with_loading_emoji(slack, "C1", "123.456", action)

        slack.remove_reaction.assert_called_once()

    def test_add_failure_does_not_break_the_work(self):
        """이모지는 부가 기능이라 붙이지 못해도 본 작업은 그대로 진행된다."""
        slack = fake_slack()
        slack.add_reaction.side_effect = RuntimeError("rate limited")
        action = MagicMock(return_value="done")

        assert with_loading_emoji(slack, "C1", "123.456", action) == "done"

        action.assert_called_once()
        # 붙이지 못했으면 떼려고도 하지 않는다
        slack.remove_reaction.assert_not_called()

    def test_remove_failure_does_not_mask_the_original_error(self):
        """삭제 실패를 올려보내면 본 작업이 남긴 예외를 덮어써 원인을 잃는다."""
        slack = fake_slack()
        slack.remove_reaction.side_effect = RuntimeError("api down")
        action = MagicMock(side_effect=ValueError("본 작업 실패"))

        with self.assertRaises(ValueError):
            with_loading_emoji(slack, "C1", "123.456", action)

    def test_remove_failure_does_not_lose_the_result(self):
        slack = fake_slack()
        slack.remove_reaction.side_effect = RuntimeError("api down")

        assert with_loading_emoji(slack, "C1", "123.456", lambda: "done") == "done"

    def test_does_nothing_without_channel_or_ts(self):
        slack = fake_slack()
        action = MagicMock(return_value="done")

        assert with_loading_emoji(slack, None, "123.456", action) == "done"
        assert with_loading_emoji(slack, "C1", None, action) == "done"

        assert action.call_count == 2
        slack.add_reaction.assert_not_called()
        slack.remove_reaction.assert_not_called()

    def test_reusable_across_sequential_calls(self):
        slack = fake_slack()

        with_loading_emoji(slack, "C1", "123.456", lambda: None)
        with_loading_emoji(slack, "C1", "123.456", lambda: None)

        assert slack.add_reaction.call_count == 2
        assert slack.remove_reaction.call_count == 2
