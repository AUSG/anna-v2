import unittest
from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from implementation.slack_client import SlackClient


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
