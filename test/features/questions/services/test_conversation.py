import pytest

from features.questions import slack as question_slack
from features.questions.models import Utterance
from features.questions.services import conversation
from features.questions.services.conversation import (
    normalize_conversation,
    select_conversation,
)
from shared.slack_events import MentionEvent
from shared.slack_models import Message
from test.fixtures.runtime import fake_slack

ANNA_ID = "UANNA"


def _message(ts, user, text):
    return Message(ts=ts, thread_ts="1", channel="C1", user=user, text=text)


def test_handler_consumes_feature_selection_policy(monkeypatch):
    assert question_slack.select_conversation is conversation.select_conversation
    assert question_slack.normalize_conversation is conversation.normalize_conversation
    monkeypatch.setattr(conversation, "MAX_CONVERSATION_MESSAGES", 2)
    slack = fake_slack()
    slack.get_thread.return_value = [
        _message("1", "U1", "root"),
        _message("2", "U2", "가나"),
        _message("3", "U3", "newest"),
    ]
    event = MentionEvent(
        text="<@UANNA> q) 가나", user="U9", channel="C1", ts="9", thread_ts="1"
    )

    selected = question_slack.fetch_conversation(
        "가나", event, slack, assistant_id=ANNA_ID
    )

    slack.get_thread.assert_called_once_with("C1", "1")
    assert selected == [
        Utterance(role="user", content="root", author="U1", timestamp="1"),
        Utterance(role="user", content="가나", author="U2", timestamp="2"),
    ]


def test_normalize_excludes_current_mention_and_blank_messages():
    normalized = normalize_conversation(
        [
            _message("1", "U1", " 첫 글 "),
            _message("2", "U2", " \t\n"),
            _message("9", "U9", "<@UANNA> q) 현재 질문"),
        ],
        current_ts="9",
        assistant_id=ANNA_ID,
    )
    assert normalized == [
        Utterance(role="user", content="첫 글", author="U1", timestamp="1")
    ]


@pytest.mark.parametrize(
    ("assistant_id", "roles"),
    [
        (ANNA_ID, ["user", "assistant", "user"]),
        ("", ["user", "user", "user"]),
        (None, ["user", "user", "user"]),
    ],
)
def test_normalize_assigns_assistant_role_only_by_assistant_id(assistant_id, roles):
    normalized = normalize_conversation(
        [
            _message("1", "BGEEK", "[GeekNews] 패스키"),
            _message("2", ANNA_ID, "안나 답변"),
            _message("3", "U1", "사람 답글"),
        ],
        current_ts="9",
        assistant_id=assistant_id,
    )
    assert [turn.role for turn in normalized] == roles
    # 다른 봇 글은 bot_id 가 작성자로 남는다
    assert [turn.author for turn in normalized] == ["BGEEK", ANNA_ID, "U1"]


def test_normalize_clips_each_field_to_its_limit():
    normalized = normalize_conversation(
        [_message("시" * 101, "작" * 201, " 😀" + "가" * 4000)],
        current_ts="9",
        assistant_id=ANNA_ID,
    )
    assert normalized == [
        Utterance(
            role="user",
            content="😀" + "가" * 3999,
            author="작" * 200,
            timestamp="시" * 100,
        )
    ]


def test_select_keeps_root_and_relevant_turn_within_message_budget(monkeypatch):
    monkeypatch.setattr(conversation, "MAX_CONVERSATION_MESSAGES", 2)
    turns = [
        Utterance(role="user", content="root"),
        Utterance(role="user", content="가나"),
        Utterance(role="user", content="newest"),
    ]

    selected = select_conversation(turns, "가나")

    assert len(selected) == 2
    assert selected[0] is turns[0]
    assert selected[1] is turns[1]
