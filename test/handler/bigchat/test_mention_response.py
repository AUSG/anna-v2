import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.shuffle_response import ShuffleResponse
from handler.bigchat.simple_response import SimpleResponse
from handler.bigchat.mention_response import MentionResponse


class TestMentionResponse(unittest.TestCase):
    def test_run_by_accepted_keyword(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 섞어줘 <@Uabc> <@Udef>")
        mock_slack_client = MagicMock()
        shuffle = ShuffleResponse(event, mock_slack_client)
        fallback = SimpleResponse(event, mock_slack_client)
        sut = MentionResponse([shuffle], fallback)

        result = sut.run()

        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] in ["여기있어!\n<@Uabc> <@Udef>", "여기있어!\n<@Udef> <@Uabc>"]

    def test_run_by_unaccepted_keyword_by_fallback(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>")
        mock_slack_client = MagicMock()
        shuffle = ShuffleResponse(event, mock_slack_client)
        fallback = SimpleResponse(event, mock_slack_client)
        sut = MentionResponse([shuffle], fallback)

        result = sut.run()

        assert result is True
        assert mock_slack_client.send_message.call_args.kwargs["msg"] == "앗, 잘못입력한 것 같아.\n나를 멘션하면서 help를 한 번 입력해봐!"
