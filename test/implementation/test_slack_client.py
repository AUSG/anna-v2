import unittest
from unittest.mock import MagicMock, patch

from slack_sdk.errors import SlackApiError

from implementation.slack_client import SlackClient


class TestSlackClient(unittest.TestCase):
    def test_send_direct_message(self):
        mock_web_client = MagicMock()
        # 스케줄 발송 컨텍스트에는 bolt 의 say 가 없다
        sut = SlackClient(say=None, web_client=mock_web_client)

        sut.send_direct_message(user_id="U0001", msg="내일 만나!")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="U0001", text="내일 만나!", unfurl_links=False, unfurl_media=False
        )

    def test_send_thread_message(self):
        mock_web_client = MagicMock()
        sut = SlackClient(MagicMock(), mock_web_client)

        sut.send_thread_message(msg="hello", channel="C03SZTDEDK3", ts="123.456")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="C03SZTDEDK3",
            text="hello",
            thread_ts="123.456",
            unfurl_links=False,
            unfurl_media=False,
        )

    def test_send_message_disables_unfurling(self):
        mock_say = MagicMock()
        sut = SlackClient(mock_say, MagicMock())

        sut.send_message(msg="https://docs.google.com/spreadsheets/d/1", ts="123.456")

        mock_say.assert_called_once_with(
            "https://docs.google.com/spreadsheets/d/1",
            thread_ts="123.456",
            unfurl_links=False,
            unfurl_media=False,
        )

    def test_send_message_to_freetalk_disables_unfurling(self):
        mock_say = MagicMock()
        sut = SlackClient(mock_say, MagicMock())

        sut.send_message_to_freetalk(msg="hello")

        mock_say.assert_called_once_with(
            "hello", channel="CQJ8HQWUV", unfurl_links=False, unfurl_media=False
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


class TestSlackClientGetEmoji(unittest.TestCase):
    def setUp(self):
        self.mock_web_client = MagicMock()
        self.sut = SlackClient(MagicMock(), self.mock_web_client)

    def test_returns_reaction_with_users(self):
        self.mock_web_client.reactions_get.return_value = {
            "message": {
                "reactions": [
                    {"name": "eyes", "users": ["U3"], "count": 1},
                    {"name": "gogo", "users": ["U1", "U2"], "count": 2},
                ]
            }
        }

        reaction = self.sut.get_emoji(channel="C1", ts="123.456", emoji_name="gogo")

        self.mock_web_client.reactions_get.assert_called_once_with(
            channel="C1", timestamp="123.456", full=True
        )
        assert reaction is not None
        assert reaction.name == "gogo"
        assert reaction.users == ["U1", "U2"]
        assert reaction.count == 2

    def test_returns_none_when_emoji_not_found(self):
        self.mock_web_client.reactions_get.return_value = {
            "message": {"reactions": [{"name": "eyes", "users": ["U3"], "count": 1}]}
        }

        assert self.sut.get_emoji(channel="C1", ts="123.456", emoji_name="gogo") is None

    def test_returns_none_when_message_has_no_reactions(self):
        self.mock_web_client.reactions_get.return_value = {"message": {}}

        assert self.sut.get_emoji(channel="C1", ts="123.456", emoji_name="gogo") is None

    def test_returns_none_on_api_error(self):
        self.mock_web_client.reactions_get.side_effect = SlackApiError(
            "message_not_found", MagicMock()
        )

        assert self.sut.get_emoji(channel="C1", ts="123.456", emoji_name="gogo") is None

    def test_retries_on_transient_os_error(self):
        self.mock_web_client.reactions_get.side_effect = [
            OSError("connection reset"),
            {"message": {"reactions": [{"name": "gogo", "users": ["U1"], "count": 1}]}},
        ]

        reaction = self.sut.get_emoji(channel="C1", ts="123.456", emoji_name="gogo")

        assert reaction is not None
        assert self.mock_web_client.reactions_get.call_count == 2

    def test_returns_none_when_os_error_persists(self):
        self.mock_web_client.reactions_get.side_effect = OSError("connection reset")

        assert self.sut.get_emoji(channel="C1", ts="123.456", emoji_name="gogo") is None
        assert self.mock_web_client.reactions_get.call_count == 3
