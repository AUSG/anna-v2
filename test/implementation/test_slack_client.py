import unittest
from unittest.mock import MagicMock, patch

from implementation.slack_client import SlackClient


class TestSlackClient(unittest.TestCase):
    def test_send_thread_message(self):
        mock_web_client = MagicMock()
        sut = SlackClient(MagicMock(), mock_web_client)

        sut.send_thread_message(msg="hello", channel="C03SZTDEDK3", ts="123.456")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="C03SZTDEDK3", text="hello", thread_ts="123.456"
        )

    @patch("implementation.slack_client.requests.post")
    def test_send_response_url_message(self, mock_post):
        sut = SlackClient(MagicMock(), MagicMock())

        sut.send_response_url_message(
            response_url="https://hooks.slack.com/app/T1/2/3", msg="hello"
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://hooks.slack.com/app/T1/2/3"
        assert kwargs["json"] == {"response_type": "ephemeral", "text": "hello"}
