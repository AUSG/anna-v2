import pytest

from features.questions import slack as question_slack
from features.questions.models import ChatFailure, ChatResult
from features.questions.presentation import answers as question_presentation
from features.questions.presentation.answers import (
    SERVICE_FAILURE_MESSAGE,
    UNTRUSTED_LINK_MARKER,
    render_parts,
)


def test_handler_uses_shared_render_helpers():
    assert question_slack.render_parts is question_presentation.render_parts
    assert UNTRUSTED_LINK_MARKER == "[확인되지 않은 링크 제거]"
    assert render_parts(ChatResult(answer="예전 답변")) == ("예전 답변", [])


@pytest.mark.parametrize("reason", ["", "timeout", "invalid json", "HTTP 503"])
def test_chat_failure_uses_service_failure_message(reason):
    assert render_parts(ChatFailure(reason)) == (
        "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.",
        [],
    )
    assert render_parts(ChatFailure(reason)) == (SERVICE_FAILURE_MESSAGE, [])


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (
            "예전 답변 https://evil.test/plain",
            "예전 답변 [확인되지 않은 링크 제거]",
        ),
        (
            "HTTPS://wrong.test www.wrong.test",
            "[확인되지 않은 링크 제거] [확인되지 않은 링크 제거]",
        ),
        (
            "<https://wrong.test|출처> [출처](https://wrong.test)",
            "출처[확인되지 않은 링크 제거] 출처[확인되지 않은 링크 제거]",
        ),
    ],
)
def test_render_parts_removes_untrusted_urls_from_uncited_answers(answer, expected):
    assert render_parts(ChatResult(answer=answer)) == (expected, [])


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("insufficient_evidence", "흐음~ 관련 기록에서는 확인하지 못했어요."),
        ("conflicting_evidence", "흐음~ 기록이 서로 달라서 확답하기 어렵네요."),
        ("answered", "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"),
        ("no_search_needed", "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"),
        ("unknown", "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"),
        ("", "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"),
    ],
)
def test_render_parts_uses_status_fallback_for_empty_answer(status, expected):
    assert render_parts(ChatResult(answer="", status=status)) == (expected, [])
