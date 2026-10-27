import unittest
from unittest.mock import MagicMock, patch

import requests
from slack_sdk.errors import SlackApiError

from integrations.slack import SlackClient

NO_UNFURL = {"unfurl_links": False, "unfurl_media": False}


class FakeResponse(dict):
    """slack_sdk 의 SlackResponse 처럼 status_code 와 ["key"] 접근을 지원한다."""

    status_code = 200


def api_error(error: str) -> SlackApiError:
    response = MagicMock()
    response.data = {"error": error}
    response.get.side_effect = response.data.get
    return SlackApiError(error, response)


class TestSendMessages(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.sut = SlackClient(self.web_client)

    def test_send_thread_message_disables_unfurling(self):
        self.sut.send_thread_message(
            "C03SZTDEDK3", "123.456", "https://docs.google.com/spreadsheets/d/1"
        )

        self.web_client.chat_postMessage.assert_called_once_with(
            channel="C03SZTDEDK3",
            thread_ts="123.456",
            text="https://docs.google.com/spreadsheets/d/1",
            blocks=None,
            **NO_UNFURL,
        )

    def test_send_thread_message_with_blocks(self):
        blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}]

        self.sut.send_thread_message("C1", "123.456", "hi", blocks)

        assert self.web_client.chat_postMessage.call_args.kwargs["blocks"] == blocks

    def test_send_channel_message_disables_unfurling(self):
        self.sut.send_channel_message("CQJ8HQWUV", "hello")

        self.web_client.chat_postMessage.assert_called_once_with(
            channel="CQJ8HQWUV", text="hello", **NO_UNFURL
        )

    def test_send_direct_message(self):
        self.sut.send_direct_message("U0001", "내일 만나!")

        self.web_client.chat_postMessage.assert_called_once_with(
            channel="U0001", text="내일 만나!", **NO_UNFURL
        )

    def test_send_ephemeral(self):
        self.sut.send_ephemeral("C1", "U0001", "너만 보여", ts="123.456")

        self.web_client.chat_postEphemeral.assert_called_once_with(
            text="너만 보여", blocks=None, channel="C1", user="U0001", thread_ts="123.456"
        )

    def test_open_view(self):
        view = {"type": "modal"}

        self.sut.open_view("trigger-1", view)

        self.web_client.views_open.assert_called_once_with(
            trigger_id="trigger-1", view=view
        )

    @patch("integrations.slack.requests.post")
    def test_send_response_url_message(self, mock_post):
        self.sut.send_response_url_message(
            "https://hooks.slack.com/app/T1/2/3", "hello"
        )

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://hooks.slack.com/app/T1/2/3"
        assert kwargs["json"] == {"response_type": "ephemeral", "text": "hello"}
        mock_post.return_value.raise_for_status.assert_called_once()


class TestSendAnswer(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.sut = SlackClient(self.web_client)

    def test_answer_goes_to_markdown_block_and_sources_to_context(self):
        self.sut.send_answer(
            "C1",
            "1.0",
            answer="### 결론\n<https://a.test|문서> 참고",
            sources=["<https://slack.ausg.me/c/C?t=1|#general>"],
        )

        kwargs = self.web_client.chat_postMessage.call_args.kwargs
        assert kwargs["blocks"] == [
            {"type": "markdown", "text": "### 결론\n[문서](https://a.test) 참고"},
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "출처: <https://slack.ausg.me/c/C?t=1|#general>",
                    }
                ],
            },
        ]
        assert kwargs["text"].endswith("출처: <https://slack.ausg.me/c/C?t=1|#general>")
        assert kwargs["channel"] == "C1" and kwargs["thread_ts"] == "1.0"
        assert kwargs["unfurl_links"] is False

    def test_without_sources_only_markdown_block_is_sent(self):
        self.sut.send_answer("C1", "1.0", answer="답", sources=[])

        kwargs = self.web_client.chat_postMessage.call_args.kwargs
        assert kwargs["blocks"] == [{"type": "markdown", "text": "답"}]
        assert kwargs["text"] == "답"

    def test_rejected_blocks_fall_back_to_plain_text(self):
        self.web_client.chat_postMessage.side_effect = [
            api_error("invalid_blocks"),
            None,
        ]

        self.sut.send_answer("C1", "1.0", answer="답", sources=[])

        assert self.web_client.chat_postMessage.call_count == 2
        kwargs = self.web_client.chat_postMessage.call_args.kwargs
        assert kwargs["text"] == "답" and kwargs["blocks"] is None

    def test_too_long_answer_is_sent_as_text(self):
        self.sut.send_answer("C1", "1.0", answer="가" * 12001, sources=[])

        self.web_client.chat_postMessage.assert_called_once()
        assert self.web_client.chat_postMessage.call_args.kwargs["blocks"] is None


class TestSendMarkdown(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.sut = SlackClient(self.web_client)

    def test_posts_markdown_block_without_unfurl(self):
        self.sut.send_markdown("C1", "**핫스레드** <https://a.test|보기>")

        kwargs = self.web_client.chat_postMessage.call_args.kwargs
        assert kwargs["channel"] == "C1" and kwargs["unfurl_links"] is False
        assert kwargs["blocks"] == [
            {"type": "markdown", "text": "**핫스레드** [보기](https://a.test)"}
        ]

    def test_rejected_blocks_fall_back_to_plain_text(self):
        self.web_client.chat_postMessage.side_effect = [
            api_error("invalid_blocks"),
            None,
        ]

        self.sut.send_markdown("C1", "글")

        assert self.web_client.chat_postMessage.call_count == 2
        kwargs = self.web_client.chat_postMessage.call_args.kwargs
        assert kwargs["text"] == "글" and "blocks" not in kwargs


class TestGetThread(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.sut = SlackClient(self.web_client)

    def test_accepts_bot_messages(self):
        self.web_client.conversations_replies.return_value = FakeResponse(
            messages=[
                {
                    "ts": "1.0",
                    "thread_ts": "1.0",
                    "bot_id": "B0450NN7ESV",
                    "text": "피드",
                },
                {"ts": "1.1", "thread_ts": "1.0", "user": "U0001", "text": "gogo"},
            ]
        )

        messages = self.sut.get_thread("C045BQPFT08", "1.0")

        self.web_client.conversations_replies.assert_called_once_with(
            ts="1.0", channel="C045BQPFT08"
        )
        assert [m.user for m in messages] == ["B0450NN7ESV", "U0001"]
        assert [m.channel for m in messages] == ["C045BQPFT08", "C045BQPFT08"]
        assert messages[0].text == "피드"

    def test_message_without_thread_ts_uses_its_own_ts(self):
        self.web_client.conversations_replies.return_value = FakeResponse(
            messages=[{"ts": "1.0", "user": "U0001", "text": "root"}]
        )

        messages = self.sut.get_thread("C1", "1.0")

        assert messages[0].thread_ts == "1.0"

    def test_retries_on_transient_os_error(self):
        self.web_client.conversations_replies.side_effect = [
            OSError("connection reset"),
            FakeResponse(messages=[{"ts": "1.0", "user": "U1", "text": "x"}]),
        ]

        messages = self.sut.get_thread("C1", "1.0")

        assert len(messages) == 1
        assert self.web_client.conversations_replies.call_count == 2

    def test_raises_when_os_error_persists(self):
        self.web_client.conversations_replies.side_effect = OSError("connection reset")

        with self.assertRaises(OSError):
            self.sut.get_thread("C1", "1.0")
        assert self.web_client.conversations_replies.call_count == 3

    def test_raises_on_non_200(self):
        response = FakeResponse(messages=[])
        response.status_code = 500
        self.web_client.conversations_replies.return_value = response

        with self.assertRaises(Exception):
            self.sut.get_thread("C1", "1.0")

    def test_get_thread_of_message_reads_the_message_then_its_thread(self):
        thread = [
            {"ts": "1.0", "thread_ts": "1.0", "user": "U1", "text": "root"},
            {"ts": "1.1", "thread_ts": "1.0", "user": "U2", "text": "reply"},
        ]

        def replies(ts, channel):
            if ts == "1.1":
                return FakeResponse(messages=[thread[1]])
            if ts == "1.0":
                return FakeResponse(messages=thread)
            raise AssertionError(ts)

        self.web_client.conversations_replies.side_effect = replies

        messages = self.sut.get_thread_of_message("C1", "1.1")

        assert [m.ts for m in messages] == ["1.0", "1.1"]
        assert [
            c.kwargs["ts"] for c in self.web_client.conversations_replies.call_args_list
        ] == ["1.1", "1.0"]

    def test_get_thread_of_message_without_replies_returns_the_message_alone(self):
        self.web_client.conversations_replies.return_value = FakeResponse(
            messages=[{"ts": "1.0", "user": "U1", "text": "alone"}]
        )

        messages = self.sut.get_thread_of_message("C1", "1.0")

        assert [m.ts for m in messages] == ["1.0"]


class TestGetReaction(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.sut = SlackClient(self.web_client)

    def test_returns_reaction_with_users(self):
        self.web_client.reactions_get.return_value = {
            "message": {
                "reactions": [
                    {"name": "eyes", "users": ["U3"], "count": 1},
                    {"name": "gogo", "users": ["U1", "U2"], "count": 2},
                ]
            }
        }

        reaction = self.sut.get_reaction("C1", "123.456", "gogo")

        self.web_client.reactions_get.assert_called_once_with(
            channel="C1", timestamp="123.456", full=True
        )
        assert reaction is not None
        assert reaction.name == "gogo"
        assert reaction.users == ["U1", "U2"]
        assert reaction.count == 2

    def test_returns_none_when_emoji_not_found(self):
        self.web_client.reactions_get.return_value = {
            "message": {"reactions": [{"name": "eyes", "users": ["U3"], "count": 1}]}
        }

        assert self.sut.get_reaction("C1", "123.456", "gogo") is None

    def test_returns_none_when_message_has_no_reactions(self):
        self.web_client.reactions_get.return_value = {"message": {}}

        assert self.sut.get_reaction("C1", "123.456", "gogo") is None

    def test_returns_none_on_api_error(self):
        self.web_client.reactions_get.side_effect = api_error("message_not_found")

        assert self.sut.get_reaction("C1", "123.456", "gogo") is None

    def test_retries_on_transient_os_error(self):
        self.web_client.reactions_get.side_effect = [
            OSError("connection reset"),
            {"message": {"reactions": [{"name": "gogo", "users": ["U1"], "count": 1}]}},
        ]

        reaction = self.sut.get_reaction("C1", "123.456", "gogo")

        assert reaction is not None
        assert self.web_client.reactions_get.call_count == 2

    def test_returns_none_when_os_error_persists(self):
        self.web_client.reactions_get.side_effect = OSError("connection reset")

        assert self.sut.get_reaction("C1", "123.456", "gogo") is None
        assert self.web_client.reactions_get.call_count == 3


class TestReactions(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.sut = SlackClient(self.web_client)

    def test_add_reaction(self):
        self.sut.add_reaction("C1", "123.456", "loading")

        self.web_client.reactions_add.assert_called_once_with(
            channel="C1", name="loading", timestamp="123.456"
        )

    def test_add_reaction_ignores_already_reacted(self):
        self.web_client.reactions_add.side_effect = api_error("already_reacted")

        self.sut.add_reaction("C1", "123.456", "loading")  # does not raise

    def test_add_reaction_raises_other_errors(self):
        self.web_client.reactions_add.side_effect = api_error("message_not_found")

        with self.assertRaises(SlackApiError):
            self.sut.add_reaction("C1", "123.456", "loading")

    def test_remove_reaction(self):
        self.sut.remove_reaction("C1", "123.456", "loading")

        self.web_client.reactions_remove.assert_called_once_with(
            channel="C1", name="loading", timestamp="123.456"
        )

    def test_remove_reaction_ignores_no_reaction(self):
        self.web_client.reactions_remove.side_effect = api_error("no_reaction")

        self.sut.remove_reaction("C1", "123.456", "loading")  # does not raise

    def test_remove_reaction_raises_other_errors(self):
        self.web_client.reactions_remove.side_effect = api_error("message_not_found")

        with self.assertRaises(SlackApiError):
            self.sut.remove_reaction("C1", "123.456", "loading")


class TestGetPermalink(unittest.TestCase):
    def test_returns_permalink(self):
        web_client = MagicMock()
        web_client.chat_getPermalink.return_value = {
            "permalink": "https://ausg.slack.com/archives/C1/p1"
        }

        permalink = SlackClient(web_client).get_permalink("C1", "1.0")

        web_client.chat_getPermalink.assert_called_once_with(
            channel="C1", message_ts="1.0"
        )
        assert permalink == "https://ausg.slack.com/archives/C1/p1"

    def test_returns_none_on_api_error(self):
        web_client = MagicMock()
        web_client.chat_getPermalink.side_effect = api_error("message_not_found")

        assert SlackClient(web_client).get_permalink("C1", "1.0") is None


class TestDownloadFile(unittest.TestCase):
    def setUp(self):
        self.web_client = MagicMock()
        self.web_client.token = "xoxb-test"
        self.sut = SlackClient(self.web_client)

    @patch("integrations.slack.requests.get")
    def test_downloads_with_bot_token(self, mock_get):
        mock_get.return_value.content = b"\x89PNG"

        content = self.sut.download_file("https://files.slack.com/a.png")

        assert content == b"\x89PNG"
        args, kwargs = mock_get.call_args
        assert args[0] == "https://files.slack.com/a.png"
        assert kwargs["headers"] == {"Authorization": "Bearer xoxb-test"}
        mock_get.return_value.raise_for_status.assert_called_once()

    @patch("integrations.slack.requests.get")
    def test_returns_none_on_http_error(self, mock_get):
        mock_get.return_value.raise_for_status.side_effect = requests.HTTPError("403")

        assert self.sut.download_file("https://files.slack.com/a.png") is None

    @patch("integrations.slack.requests.get")
    def test_returns_none_on_connection_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError()

        assert self.sut.download_file("https://files.slack.com/a.png") is None
