from unittest.mock import MagicMock

import pytest

from features.questions.models import (
    MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGES,
    ChatFailure,
    ChatResult,
    Question,
    Source,
    Utterance,
)
from features.questions.ports import QAGateway
from features.questions.presentation.answers import SERVICE_FAILURE_MESSAGE
from features.questions.slack import (
    DEFAULT_SYSTEM_PROMPT,
    UNPARSEABLE_QUESTION_MESSAGE,
    answer_question,
    fetch_conversation,
)
from shared.slack_events import MentionEvent
from shared.slack_models import Message
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import create_sample_app_mention_event

ANNA_ID = "UANNA"
_DEFAULT_ANSWER = "답변이야!"
_QUESTION_TEXT = f"<@{ANNA_ID}> q) 질문"


def _event(text=_QUESTION_TEXT, *, in_thread=False, **overrides):
    payload = create_sample_app_mention_event(text)
    if not in_thread:
        # 스레드 밖(채널 최상단)에서의 멘션에는 thread_ts 가 없다
        del payload["thread_ts"]
    payload.update(overrides)
    return MentionEvent.from_payload(payload)


def _message(ts, user, text, channel="C03SZTDEDK3", thread_ts="1689403100.222939"):
    return Message(ts=ts, thread_ts=thread_ts, channel=channel, user=user, text=text)


def _make():
    slack = fake_slack()
    qa = MagicMock(spec=QAGateway)
    qa.chat.return_value = ChatResult(answer=_DEFAULT_ANSWER)
    return slack, qa


def _answer(question, event, slack, qa, assistant_id=ANNA_ID):
    return answer_question(
        Question(question, explicit=True), event, slack, qa, assistant_id=assistant_id
    )


@pytest.mark.parametrize(
    ("result", "answer", "sources"),
    [
        (ChatResult(answer=_DEFAULT_ANSWER), _DEFAULT_ANSWER, []),
        (
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
        (ChatFailure("timeout"), SERVICE_FAILURE_MESSAGE, []),
    ],
    ids=["plain", "structured", "failure"],
)
def test_top_level_mention_sends_question_to_qa_and_returns_rendered_answer(
    result, answer, sources
):
    slack, qa = _make()
    qa.chat.return_value = result
    event = _event()
    trace = MagicMock()
    trace.attach_mock(slack.get_thread, "thread")
    trace.attach_mock(qa.chat, "chat")
    trace.attach_mock(slack.send_answer, "answer")

    assert _answer("RAG가 뭐야", event, slack, qa) is True

    # 스레드 밖 멘션은 스레드를 읽지 않는다
    slack.get_thread.assert_not_called()
    qa.chat.assert_called_once_with(
        question="RAG가 뭐야", conversation=[], system_prompt=DEFAULT_SYSTEM_PROMPT
    )
    slack.send_answer.assert_called_once_with(event.channel, event.ts, answer, sources)
    assert [call[0] for call in trace.mock_calls] == ["chat", "answer"]
    slack.send_thread_message.assert_not_called()


def test_empty_question_shows_usage_without_calling_qa():
    slack, qa = _make()
    event = _event(f"<@{ANNA_ID}> q)", in_thread=True)

    assert _answer("", event, slack, qa) is True

    qa.chat.assert_not_called()
    slack.get_thread.assert_not_called()
    slack.send_thread_message.assert_called_once_with(
        event.channel, event.ts, UNPARSEABLE_QUESTION_MESSAGE
    )
    slack.send_answer.assert_not_called()


def test_thread_mention_reads_the_thread_before_asking():
    slack, qa = _make()
    event = _event(in_thread=True)
    slack.get_thread.return_value = [_message("1", "U1", "원래 질문")]
    trace = MagicMock()
    trace.attach_mock(slack.get_thread, "thread")
    trace.attach_mock(qa.chat, "chat")
    trace.attach_mock(slack.send_answer, "answer")

    assert _answer("질문", event, slack, qa) is True

    slack.get_thread.assert_called_once_with("C03SZTDEDK3", "1689403100.222939")
    assert qa.chat.call_args.kwargs["conversation"] == [
        Utterance(role="user", content="원래 질문", author="U1", timestamp="1")
    ]
    assert [call[0] for call in trace.mock_calls] == ["thread", "chat", "answer"]


class TestConversationRoles:
    def _conversation(self, replies, assistant_id=ANNA_ID):
        slack = fake_slack()
        slack.get_thread.return_value = replies
        event = _event(f"<@{ANNA_ID}> 스레드 요약해줘", in_thread=True, ts="9", thread_ts="1")
        return fetch_conversation("스레드 요약해줘", event, slack, assistant_id=assistant_id)

    def test_other_bot_root_is_user_evidence_not_assistant(self):
        # 다른 봇(GeekNews 등)은 user 가 없어 bot_id 가 author 로 들어온다
        turns = self._conversation(
            [
                _message("1", "BGEEK", "[GeekNews] 패스키"),
                _message("2", ANNA_ID, "예전 안나 답변"),
                _message("3", "U1", "사람 답글"),
            ]
        )
        assert [(t.role, t.author) for t in turns] == [
            ("user", "BGEEK"),
            ("assistant", ANNA_ID),
            ("user", "U1"),
        ]

    def test_without_assistant_id_nobody_is_assistant(self):
        turns = self._conversation(
            [_message("1", "BGEEK", "봇 글"), _message("2", ANNA_ID, "안나 글")],
            assistant_id="",
        )
        assert [t.role for t in turns] == ["user", "user"]


@pytest.mark.parametrize("thread_ts", [None, ""])
def test_missing_thread_never_fetches(thread_ts):
    slack = fake_slack()
    event = _event(in_thread=True, thread_ts=thread_ts)

    assert fetch_conversation("질문", event, slack, assistant_id=ANNA_ID) == []
    slack.get_thread.assert_not_called()


@pytest.mark.parametrize("messages", [[], [_message("1", "U1", " \t\n")]])
def test_empty_normalized_history_is_empty_conversation(messages):
    slack = fake_slack()
    slack.get_thread.return_value = messages

    assert (
        fetch_conversation("질문", _event(in_thread=True), slack, assistant_id=ANNA_ID)
        == []
    )


def test_fetch_failure_is_logged_but_does_not_prevent_qa_reply(caplog):
    slack, qa = _make()
    slack.get_thread.side_effect = RuntimeError("조회 실패")
    event = _event(in_thread=True)

    assert _answer("질문", event, slack, qa) is True

    assert qa.chat.call_args.kwargs["conversation"] == []
    slack.send_answer.assert_called_once_with(
        event.channel, event.ts, _DEFAULT_ANSWER, []
    )
    assert "Failed to fetch thread context: 조회 실패" in [
        record.getMessage() for record in caplog.records
    ]


def test_current_event_filter_and_unicode_clipping_are_preserved():
    slack = fake_slack()
    event = _event(f"<@{ANNA_ID}> q) 현재 질문", in_thread=True)
    slack.get_thread.return_value = [
        _message(event.ts, "U9", "  <@UANNA> q) 현재 질문  "),
        _message("2", "U1", "<@UANNA> q) 현재 질문"),
        _message("3", ANNA_ID, " 안나\r\n답 😀 "),
        _message("4", "B1", "다른 봇"),
        _message("5", "", "작성자 없음"),
        _message("6", "U6", " \t\n"),
        _message("시" * 101, "작" * 201, " 😀" + "가" * 4000),
    ]

    assert fetch_conversation("현재 질문", event, slack, assistant_id=ANNA_ID) == [
        Utterance(role="user", content="<@UANNA> q) 현재 질문", author="U1", timestamp="2"),
        Utterance(role="assistant", content="안나\r\n답 😀", author=ANNA_ID, timestamp="3"),
        Utterance(role="user", content="다른 봇", author="B1", timestamp="4"),
        Utterance(role="user", content="작성자 없음", author="", timestamp="5"),
        Utterance(
            role="user",
            content="😀" + "가" * 3999,
            author="작" * 200,
            timestamp="시" * 100,
        ),
    ]
    slack.get_thread.assert_called_once_with(event.channel, event.thread_ts)


@pytest.mark.parametrize("failure", ["qa", "send"])
def test_qa_and_send_failures_propagate_after_existing_call_order(failure):
    slack, qa = _make()
    event = _event(in_thread=True)
    trace = MagicMock()
    trace.attach_mock(slack.get_thread, "thread")
    trace.attach_mock(qa.chat, "chat")
    trace.attach_mock(slack.send_answer, "answer")
    if failure == "qa":
        qa.chat.side_effect = RuntimeError("QA 실패")
    else:
        slack.send_answer.side_effect = RuntimeError("전송 실패")

    with pytest.raises(RuntimeError, match="실패"):
        _answer("질문", event, slack, qa)
    expected = ["thread", "chat"] if failure == "qa" else ["thread", "chat", "answer"]
    assert [call[0] for call in trace.mock_calls] == expected
    slack.send_thread_message.assert_not_called()


def test_handler_keeps_current_question_separate_and_preserves_identities():
    slack, qa = _make()
    event = _event(
        f"<@{ANNA_ID}> q) 지금 뭐야?",
        in_thread=True,
        ts="3",
        thread_ts="1",
        channel="C1",
        user="U2",
    )
    slack.get_thread.return_value = [
        _message("1", "U1", "원래 질문", channel="C1", thread_ts="1"),
        _message("2", ANNA_ID, "제가 답했어요", channel="C1", thread_ts="1"),
        _message("3", "U2", f"<@{ANNA_ID}> q) 지금 뭐야?", channel="C1", thread_ts="1"),
    ]

    assert _answer("지금 뭐야?", event, slack, qa) is True

    slack.get_thread.assert_called_once_with("C1", "1")
    assert qa.chat.call_args.kwargs["question"] == "지금 뭐야?"
    assert qa.chat.call_args.kwargs["conversation"] == [
        Utterance(role="user", content="원래 질문", author="U1", timestamp="1"),
        Utterance(role="assistant", content="제가 답했어요", author=ANNA_ID, timestamp="2"),
    ]


def test_handler_bounds_history_to_root_and_recent_turns():
    slack, qa = _make()
    event = _event(in_thread=True, ts="99", thread_ts="1")
    slack.get_thread.return_value = [
        _message(str(i), f"U{i}", f"메시지-{i}" * 2000) for i in range(50)
    ]

    assert _answer("질문", event, slack, qa) is True
    conversation = qa.chat.call_args.kwargs["conversation"]

    assert len(conversation) <= MAX_CONVERSATION_MESSAGES
    assert sum(len(item.content) for item in conversation) <= MAX_CONVERSATION_CHARS
    assert conversation[0].content.startswith("메시지-0")
    assert conversation[-1].content.startswith("메시지-49")


def test_handler_prioritizes_a_relevant_middle_turn_before_filler():
    slack, qa = _make()
    event = _event(f"<@{ANNA_ID}> q) Kubernetes 일정", in_thread=True, ts="99")
    messages = [_message(str(i), f"U{i}", f"무관한 메시지 {i}" * 1000) for i in range(20)]
    messages[10] = _message("10", "U10", "Kubernetes 일정은 10월이에요" * 1000)
    slack.get_thread.return_value = messages

    assert _answer("Kubernetes 일정", event, slack, qa) is True
    conversation = qa.chat.call_args.kwargs["conversation"]

    assert any("Kubernetes" in item.content for item in conversation)
