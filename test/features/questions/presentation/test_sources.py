from unittest.mock import MagicMock

import pytest

from features.questions.presentation import answers as question_presentation
from features.questions import slack as question_response
from features.questions.slack import QuestionResponse
from features.questions.models import ChatResult


def test_handler_uses_shared_render_helpers_and_accepts_string_results():
    assert question_response.render_parts is question_presentation.render_parts
    assert question_presentation.UNTRUSTED_LINK_MARKER == "[확인되지 않은 링크 제거]"
    assert QuestionResponse._render_parts("예전 답변") == ("예전 답변", [])
    assert QuestionResponse._render_result("예전 답변") == "예전 답변"


def test_render_result_none_uses_service_failure_message():
    assert QuestionResponse._render_result(None) == (
        "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요."
    )


@pytest.mark.parametrize(
    ("result", "expected"),
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
def test_render_result_removes_untrusted_urls(result, expected):
    assert QuestionResponse._render_result(result) == expected


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
def test_render_result_uses_status_fallback_for_empty_answer(status, expected):
    assert (
        QuestionResponse._render_result(ChatResult(answer="", status=status))
        == expected
    )


def test_render_result_calls_class_render_parts(monkeypatch):
    result = object()
    render_parts = MagicMock(return_value=("교체 답변", ["첫 출처", "둘째 출처"]))
    monkeypatch.setattr(QuestionResponse, "_render_parts", staticmethod(render_parts))

    assert QuestionResponse._render_result(result) == "교체 답변\n\n출처: 첫 출처, 둘째 출처"
    render_parts.assert_called_once_with(result)
