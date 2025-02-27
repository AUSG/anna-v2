import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.simple_response import SimpleResponse


class TestSimpleResponse(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>")
        mock_slack_client = MagicMock()
        sut = SimpleResponse(event, mock_slack_client)

        result = sut.handle_mention()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] == "앗, 잘못입력한 것 같아.\n나를 멘션하면서 help를 한 번 입력해봐!"

    def test_run_by_text_not_empty(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 안녕?")
        mock_slack_client = MagicMock()
        sut = SimpleResponse(event, mock_slack_client)

        result = sut.handle_mention()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] == "앗, 잘못입력한 것 같아.\n나를 멘션하면서 help를 한 번 입력해봐!"
