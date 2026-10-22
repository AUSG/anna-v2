import unittest
from unittest.mock import MagicMock

import pytest

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.question_response import QuestionResponse


def _make(text, require_prefix=True):
    event = create_sample_app_mention_event(text)
    slack_client = MagicMock()
    slack_client.get_replies.return_value = []
    qa_client = MagicMock()
    qa_client.chat.return_value = "답변이야!"
    sut = QuestionResponse(
        event, slack_client, qa_client, require_prefix=require_prefix
    )
    return sut, slack_client, qa_client


@pytest.mark.parametrize(
    ("text", "require_prefix"),
    [
        ("<@U01BN035Y6L> q) RAG가 뭐야", True),
        ("<@U01BN035Y6L> RAG가 뭐야", False),
    ],
)
def test_sends_question_to_qa_and_returns_answer(text, require_prefix):
    sut, slack_client, qa_client = _make(text, require_prefix=require_prefix)

    assert sut.handle_mention() is True
    qa_client.chat.assert_called_once()
    assert qa_client.chat.call_args.kwargs["question"] == "RAG가 뭐야"
    slack_client.send_answer.assert_called_once()
    assert slack_client.send_answer.call_args.kwargs["answer"] == "답변이야!"


@pytest.mark.parametrize(
    ("text", "require_prefix"),
    [
        ("<@U01BN035Y6L> RAG가 뭐야", True),
        ("<@U01BN035Y6L>", False),
    ],
)
def test_ignores_mentions_outside_question_mode(text, require_prefix):
    sut, slack_client, qa_client = _make(text, require_prefix=require_prefix)

    assert sut.handle_mention() is False
    qa_client.chat.assert_not_called()
    slack_client.send_message.assert_not_called()
    slack_client.send_answer.assert_not_called()


def test_empty_explicit_question_shows_usage_without_calling_qa():
    sut, slack_client, qa_client = _make("<@U01BN035Y6L> q)")

    assert sut.handle_mention() is True
    qa_client.chat.assert_not_called()
    slack_client.send_message.assert_called_once()
    assert "질문을 이해하지 못했어요" in slack_client.send_message.call_args.kwargs["msg"]
    slack_client.send_answer.assert_not_called()


class TestConversationRoles(unittest.TestCase):
    def _conversation(self, replies, assistant_id="UANNA"):
        event = {
            "text": "<@UANNA> 스레드 요약해줘",
            "ts": "9",
            "channel": "C",
            "thread_ts": "1",
        }
        slack_client = MagicMock()
        slack_client.get_replies.return_value = replies
        sut = QuestionResponse(
            event,
            slack_client,
            MagicMock(),
            require_prefix=False,
            assistant_id=assistant_id,
        )
        return sut._fetch_conversation()

    def test_other_bot_root_is_user_evidence_not_assistant(self):
        turns = self._conversation(
            [
                {
                    "ts": "1",
                    "bot_id": "BGEEK",
                    "username": "GeekNews",
                    "text": "[GeekNews] 패스키",
                },
                {"ts": "2", "user": "UANNA", "bot_id": "BANNA", "text": "예전 안나 답변"},
                {"ts": "3", "user": "U1", "text": "사람 답글"},
            ]
        )
        assert [(t["role"], t.get("author")) for t in turns] == [
            ("user", "GeekNews"),
            ("assistant", "UANNA"),
            ("user", "U1"),
        ]

    def test_without_assistant_id_bots_are_still_assistant(self):
        turns = self._conversation(
            [{"ts": "1", "bot_id": "BGEEK", "text": "봇 글"}], assistant_id=""
        )
        assert turns[0]["role"] == "assistant"
