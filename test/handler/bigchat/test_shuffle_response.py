import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.shuffle_response import ShuffleResponse


class TestShuffleResponse(unittest.TestCase):
    def test_run_by_korean(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 섞어줘 <@Uabc> <@Udef>")
        mock_slack_client = MagicMock()
        sut = ShuffleResponse(event, mock_slack_client)

        result = sut.handle_mention()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] in ["여기있어!\n<@Uabc> <@Udef>", "여기있어!\n<@Udef> <@Uabc>"]

    def test_run_by_english(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> shuffle <@Uabc> <@Udef>")
        mock_slack_client = MagicMock()
        sut = ShuffleResponse(event, mock_slack_client)

        result = sut.handle_mention()

        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] in ["여기있어!\n<@Uabc> <@Udef>", "여기있어!\n<@Udef> <@Uabc>"]
