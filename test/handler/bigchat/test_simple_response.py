import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.simple_response import SimpleResponse


class TestSimpleResponse(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>")
        mock_slack_client = MagicMock()
        sut = SimpleResponse(event, mock_slack_client)

        result = sut.run()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] == "?"

    def test_not_run_by_text_not_empty(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 안녕?")
        mock_slack_client = MagicMock()
        sut = SimpleResponse(event, mock_slack_client)

        result = sut.run()

        mock_slack_client.send_message.assert_not_called()
        assert result is False
