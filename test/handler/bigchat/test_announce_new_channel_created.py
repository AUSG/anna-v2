import unittest
from unittest.mock import MagicMock

from handler.bigchat.announce_new_channel_created import AnnounceNewChannelCreated
from test.handler.bigchat.sample_data import create_sample_channel_created_event


class TestAnnounceNewChannelCreated(unittest.TestCase):
    def test_run(self):
        event = create_sample_channel_created_event("C1234567890")
        mock_slack_client = MagicMock()
        sut = AnnounceNewChannelCreated(event, mock_slack_client)

        result = sut.run()

        mock_slack_client.send_message_to_freetalk.assert_called_once()
        assert result is True
        assert mock_slack_client.send_message_to_freetalk.call_args.kwargs["msg"] == '새로운 채널이 만들어졌어! <#C1234567890>'
