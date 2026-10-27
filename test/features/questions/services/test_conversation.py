from unittest.mock import MagicMock

from features.questions.services import conversation
from features.questions import slack as question_response


def test_handler_consumes_feature_selection_policy(monkeypatch):
    assert question_response.select_conversation is conversation.select_conversation
    monkeypatch.setattr(conversation, "MAX_CONVERSATION_MESSAGES", 2)
    turns = [
        {"role": "user", "content": "root"},
        {"role": "user", "content": "가나"},
        {"role": "user", "content": "newest"},
    ]
    slack = MagicMock()
    handler = question_response.QuestionResponse(
        {"text": "<@UANNA> q) 가나", "ts": "9", "channel": "C1", "thread_ts": "1"},
        slack,
        None,
    )
    handler._normalize_conversation = lambda messages: turns
    selected = handler._fetch_conversation()

    slack.get_replies.assert_called_once_with(channel="C1", thread_ts="1")
    assert len(selected) == 2
    assert selected[0] is turns[0]
    assert selected[1] is turns[1]
