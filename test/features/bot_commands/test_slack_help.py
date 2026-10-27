import unittest
from unittest.mock import MagicMock

from test.fixtures.slack_events import create_sample_app_mention_event

from features.bot_commands.slack import HelpResponse


class TestHelpResponse(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 도움!")
        mock_slack_client = MagicMock()
        sut = HelpResponse(event, mock_slack_client)

        result = sut.handle_mention()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"].startswith(
            "나를 멘션했을 때, 사용할 수 있는 명령어야"
        )

    def test_run_by_english(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> help!")
        mock_slack_client = MagicMock()
        sut = HelpResponse(event, mock_slack_client)

        result = sut.handle_mention()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"].startswith(
            "나를 멘션했을 때, 사용할 수 있는 명령어야"
        )
