import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from test.fixtures.slack_events import create_sample_app_mention_event

from features.questions.models import (
    MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGES,
    ChatResult,
    Source,
)
from features.questions.handlers.question_response import (
    DEFAULT_SYSTEM_PROMPT,
    QuestionResponse,
)
from integrations.slack import Message

_DEFAULT_ANSWER = "답변이야!"
_QUESTION_TEXT = "<@UANNA> q) 질문"


def _make(text="", require_prefix=True, *, event=None, assistant_id=None):
    if event is None:
        event = create_sample_app_mention_event(text)
    slack_client = MagicMock()
    slack_client.get_replies.return_value = []
    qa_client = MagicMock()
    qa_client.chat.return_value = _DEFAULT_ANSWER
    sut = QuestionResponse(
        event,
        slack_client,
        qa_client,
        require_prefix=require_prefix,
        assistant_id=assistant_id,
    )
    return sut, slack_client, qa_client


@pytest.mark.parametrize(
    ("text", "require_prefix", "result", "answer", "sources"),
    [
        ("<@U01BN035Y6L> q) RAG가 뭐야", True, _DEFAULT_ANSWER, _DEFAULT_ANSWER, []),
        ("<@U01BN035Y6L> RAG가 뭐야", False, _DEFAULT_ANSWER, _DEFAULT_ANSWER, []),
        (
            "<@U01BN035Y6L> q) RAG가 뭐야",
            True,
            ChatResult(
                answer="확인했어요.",
                citations=["doc-1"],
                sources=[
                    Source(
                        document_id="doc-1", title="#공지", url="https://example.test/1"
                    )
                ],
            ),
            "확인했어요.",
            ["<https://example.test/1|#공지>"],
        ),
    ],
    ids=["explicit-legacy", "fallback-legacy", "structured"],
)
def test_sends_question_to_qa_and_returns_answer(
    text, require_prefix, result, answer, sources
):
    sut, slack_client, qa_client = _make(text, require_prefix=require_prefix)
    qa_client.chat.return_value = result
    trace = MagicMock()
    trace.attach_mock(slack_client.get_replies, "replies")
    trace.attach_mock(qa_client.chat, "chat")
    trace.attach_mock(slack_client.send_answer, "answer")

    assert sut.handle_mention() is True
    slack_client.get_replies.assert_called_once_with(
        channel="C03SZTDEDK3", thread_ts="1689403100.222939"
    )
    qa_client.chat.assert_called_once_with(
        question="RAG가 뭐야", conversation=[], system_prompt=DEFAULT_SYSTEM_PROMPT
    )
    slack_client.send_answer.assert_called_once_with(
        answer=answer, sources=sources, ts="1689403771.805849"
    )
    assert [call[0] for call in trace.mock_calls] == ["replies", "chat", "answer"]
    slack_client.send_message.assert_not_called()


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
        sut, slack, _ = _make(
            require_prefix=False,
            event={
                "text": "<@UANNA> 스레드 요약해줘",
                "ts": "9",
                "channel": "C",
                "thread_ts": "1",
            },
            assistant_id=assistant_id,
        )
        slack.get_replies.return_value = replies
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


@pytest.mark.parametrize(
    ("attribute", "value"),
    [("channel", None), ("thread_ts", None)],
)
def test_missing_channel_or_thread_has_no_conversation(attribute, value):
    sut, slack, _ = _make(_QUESTION_TEXT)
    setattr(sut, attribute, value)

    assert sut._fetch_conversation() == []
    slack.get_replies.assert_not_called()


@pytest.mark.parametrize("messages", [None, [], [{"ts": "1", "text": " \t\n"}]])
def test_empty_history_has_no_conversation(messages):
    sut, slack, _ = _make(_QUESTION_TEXT)
    slack.get_replies.return_value = messages

    assert sut._fetch_conversation() == []


def test_fetch_failure_is_logged_but_does_not_prevent_qa_reply(caplog):
    sut, slack, qa = _make(_QUESTION_TEXT)
    slack.get_replies.side_effect = RuntimeError("조회 실패")

    assert sut.handle_mention() is True
    assert qa.chat.call_args.kwargs["conversation"] == []
    slack.send_answer.assert_called_once_with(
        answer=_DEFAULT_ANSWER, sources=[], ts=sut.ts
    )
    assert [record.getMessage() for record in caplog.records] == [
        "Failed to fetch thread context: 조회 실패"
    ]


def test_sdk_values_current_event_filter_and_unicode_clipping_are_preserved():
    sut, slack, _ = _make("<@UANNA> q) 현재 질문")
    sut.assistant_id = "UANNA"
    slack.get_replies.return_value = [
        SimpleNamespace(ts=sut.ts, text=object()),
        {"text": "  <@UANNA> q) 현재 질문  "},
        {"ts": "2", "text": "<@UANNA> q) 현재 질문", "user": "U1"},
        SimpleNamespace(ts="3", text=" 안나\r\n답\u2028😀 ", user="UANNA"),
        {"ts": "4", "text": "다른 봇", "user": 42, "username": "GeekNews", "bot_id": "B1"},
        {"ts": "5", "text": "작성자 우선", "author": "author", "username": "username"},
        {"ts": 42, "text": "형식 유지", "user": None, "author": [], "username": False},
        SimpleNamespace(ts="시" * 101, text=" 😀" + "가" * 4000, user="작" * 201),
    ]

    assert sut._fetch_conversation() == [
        {
            "role": "user",
            "content": "<@UANNA> q) 현재 질문",
            "author": "U1",
            "timestamp": "2",
        },
        {
            "role": "assistant",
            "content": "안나\r\n답\u2028😀",
            "author": "UANNA",
            "timestamp": "3",
        },
        {"role": "user", "content": "다른 봇", "author": "GeekNews", "timestamp": "4"},
        {"role": "user", "content": "작성자 우선", "author": "author", "timestamp": "5"},
        {"role": "user", "content": "형식 유지"},
        {
            "role": "user",
            "content": "😀" + "가" * 3999,
            "author": "작" * 200,
            "timestamp": "시" * 100,
        },
    ]
    slack.get_replies.assert_called_once_with(
        channel=sut.channel, thread_ts=sut.thread_ts
    )


def test_handler_keeps_current_question_separate_and_preserves_identities():
    sut, slack, qa = _make(
        event={
            "text": "<@UANNA> q) 지금 뭐야?",
            "ts": "3",
            "channel": "C1",
            "thread_ts": "1",
            "user": "U2",
        },
        assistant_id="UANNA",
    )
    slack.get_replies.return_value = [
        Message(ts="1", thread_ts="1", channel="C1", user="U1", text="원래 질문"),
        {"ts": "2", "user": "UANNA", "text": "제가 답했어요", "bot_id": "B1"},
        {"ts": "3", "user": "U2", "text": "<@UANNA> q) 지금 뭐야?"},
    ]
    qa.chat.return_value = "답변"

    assert sut.handle_mention() is True
    assert qa.chat.call_args.kwargs["question"] == "지금 뭐야?"
    assert qa.chat.call_args.kwargs["conversation"] == [
        {"role": "user", "content": "원래 질문", "author": "U1", "timestamp": "1"},
        {
            "role": "assistant",
            "content": "제가 답했어요",
            "author": "UANNA",
            "timestamp": "2",
        },
    ]


def test_handler_bounds_history_to_root_and_recent_turns():
    sut, slack, qa = _make(
        event={"text": _QUESTION_TEXT, "ts": "99", "channel": "C1", "thread_ts": "1"}
    )
    slack.get_replies.return_value = [
        {"ts": str(i), "user": f"U{i}", "text": f"메시지-{i}" * 2000} for i in range(50)
    ]
    qa.chat.return_value = "답변"

    assert sut.handle_mention() is True
    conversation = qa.chat.call_args.kwargs["conversation"]

    assert len(conversation) <= MAX_CONVERSATION_MESSAGES
    assert sum(len(item["content"]) for item in conversation) <= MAX_CONVERSATION_CHARS
    assert conversation[0]["content"].startswith("메시지-0")
    assert conversation[-1]["content"].startswith("메시지-49")
