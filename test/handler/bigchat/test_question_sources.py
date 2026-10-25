from unittest.mock import MagicMock

from handler.bigchat import question_presentation, question_response
from handler.bigchat.question_response import QuestionResponse


def test_private_helpers_and_legacy_methods_remain_available_at_old_path():
    assert question_response._safe_source_url is question_presentation._safe_source_url
    assert (
        question_response._normalize_answer_url
        is question_presentation._normalize_answer_url
    )
    assert (
        question_response._format_timestamp is question_presentation._format_timestamp
    )
    assert (
        question_response._strip_untrusted_answer_links
        is question_presentation._strip_untrusted_answer_links
    )
    assert (
        question_response._escape_slack_text is question_presentation._escape_slack_text
    )
    assert question_response.UNTRUSTED_LINK_MARKER == "[확인되지 않은 링크 제거]"
    assert QuestionResponse._render_parts("예전 답변") == ("예전 답변", [])
    assert QuestionResponse._render_result("예전 답변") == "예전 답변"


def test_legacy_render_result_uses_patched_class_render_parts(monkeypatch):
    result = object()
    render_parts = MagicMock(return_value=("교체 답변", ["첫 출처", "둘째 출처"]))
    monkeypatch.setattr(QuestionResponse, "_render_parts", staticmethod(render_parts))

    assert QuestionResponse._render_result(result) == "교체 답변\n\n출처: 첫 출처, 둘째 출처"
    render_parts.assert_called_once_with(result)
