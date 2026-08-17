import unittest
from unittest.mock import MagicMock

from handler.loading_emoji import LoadingEmoji


class TestLoadingEmoji(unittest.TestCase):
    def test_adds_on_enter_and_removes_on_exit(self):
        mock_slack_client = MagicMock()

        with LoadingEmoji(mock_slack_client, "C1", "123.456"):
            mock_slack_client.add_emoji.assert_called_once_with(
                "C1", "123.456", "loading"
            )
            mock_slack_client.remove_emoji.assert_not_called()

        mock_slack_client.remove_emoji.assert_called_once_with(
            "C1", "123.456", "loading"
        )

    def test_removes_even_when_body_raises(self):
        mock_slack_client = MagicMock()

        with self.assertRaises(RuntimeError):
            with LoadingEmoji(mock_slack_client, "C1", "123.456"):
                raise RuntimeError("boom")

        mock_slack_client.remove_emoji.assert_called_once()

    def test_add_failure_does_not_break_the_work(self):
        """이모지는 부가 기능이라 붙이지 못해도 본 작업은 그대로 진행된다."""
        mock_slack_client = MagicMock()
        mock_slack_client.add_emoji.side_effect = RuntimeError("rate limited")
        ran = False

        with LoadingEmoji(mock_slack_client, "C1", "123.456"):
            ran = True

        assert ran
        # 붙이지 못했으면 떼려고도 하지 않는다
        mock_slack_client.remove_emoji.assert_not_called()

    def test_remove_failure_does_not_mask_the_original_error(self):
        """삭제 실패를 올려보내면 본 작업이 남긴 예외를 덮어써 원인을 잃는다."""
        mock_slack_client = MagicMock()
        mock_slack_client.remove_emoji.side_effect = RuntimeError("api down")

        with self.assertRaises(ValueError):
            with LoadingEmoji(mock_slack_client, "C1", "123.456"):
                raise ValueError("본 작업 실패")

    def test_does_nothing_without_channel_or_ts(self):
        mock_slack_client = MagicMock()

        with LoadingEmoji(mock_slack_client, None, "123.456"):
            pass
        with LoadingEmoji(mock_slack_client, "C1", None):
            pass

        mock_slack_client.add_emoji.assert_not_called()
        mock_slack_client.remove_emoji.assert_not_called()

    def test_reusable_across_sequential_blocks(self):
        mock_slack_client = MagicMock()
        sut = LoadingEmoji(mock_slack_client, "C1", "123.456")

        with sut:
            pass
        with sut:
            pass

        assert mock_slack_client.add_emoji.call_count == 2
        assert mock_slack_client.remove_emoji.call_count == 2
