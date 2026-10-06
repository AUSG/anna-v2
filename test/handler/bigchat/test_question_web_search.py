import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.question_response import (
    DEFAULT_SYSTEM_PROMPT,
    UNTRUSTED_LINK_MARKER,
    WEB_SEARCH_QUERY_PROMPT,
    QuestionResponse,
    _parse_web_query,
)
from implementation.qa_client import ChatResult, Source
from implementation.web_search_client import WebSearchResult

NOT_FOUND = ChatResult(answer="", status="insufficient_evidence")
WEB_HIT = WebSearchResult(
    title="re:Invent 2026",
    url="https://reinvent.awsevents.com/",
    content="12월 1일부터 라스베이거스에서 열립니다.",
    published_date="2026-09-01",
)


def _make(text="<@U01BN035Y6L> q) re:Invent 2026 언제야?", replies=None, web=True):
    event = create_sample_app_mention_event(text)
    slack_client = MagicMock()
    slack_client.get_replies.return_value = replies or []
    qa_client = MagicMock()
    web_search_client = MagicMock() if web else None
    sut = QuestionResponse(
        event, slack_client, qa_client, web_search_client=web_search_client
    )
    return sut, slack_client, qa_client, web_search_client


class TestWebSearchTrigger(unittest.TestCase):
    def test_insufficient_evidence_triggers_search_and_second_answer(self):
        sut, slack_client, qa_client, web = _make()
        qa_client.generate.return_value = "AWS re:Invent 2026 일정"
        web.search.return_value = [WEB_HIT]
        answered = ChatResult(
            answer="웹에서 찾아보니 [re:Invent 2026](https://reinvent.awsevents.com/)은 12월 1일부터예요."
        )
        qa_client.chat.side_effect = [NOT_FOUND, answered]

        assert sut.handle_mention() is True

        # 검색어는 LLM 이 정하고, 그 검색어로 웹을 찾는다
        assert qa_client.generate.call_args.kwargs["system_prompt"] == WEB_SEARCH_QUERY_PROMPT
        assert "re:Invent 2026 언제야?" in qa_client.generate.call_args.kwargs["content"]
        web.search.assert_called_once_with("AWS re:Invent 2026 일정")

        # 두 번째 질의는 같은 질문에 웹 근거를 붙인 시스템 프롬프트로 간다
        assert qa_client.chat.call_count == 2
        first, second = qa_client.chat.call_args_list
        assert first.kwargs["system_prompt"] == DEFAULT_SYSTEM_PROMPT
        assert second.kwargs["question"] == first.kwargs["question"]
        assert second.kwargs["system_prompt"].startswith(DEFAULT_SYSTEM_PROMPT)
        assert "검색어: AWS re:Invent 2026 일정" in second.kwargs["system_prompt"]
        assert "URL: https://reinvent.awsevents.com/" in second.kwargs["system_prompt"]
        assert "12월 1일부터 라스베이거스" in second.kwargs["system_prompt"]

        # 웹 링크는 답변에 남고, 인용된 페이지는 출처에 '웹' 표시로 붙는다
        sent = slack_client.send_answer.call_args.kwargs
        assert sent["answer"] == answered.answer
        assert UNTRUSTED_LINK_MARKER not in sent["answer"]
        assert sent["sources"] == ["<https://reinvent.awsevents.com/|re:Invent 2026 · 웹>"]

    def test_answered_question_does_not_search(self):
        sut, slack_client, qa_client, web = _make()
        qa_client.chat.return_value = ChatResult(answer="기록에 있어요")

        sut.handle_mention()

        web.search.assert_not_called()
        qa_client.generate.assert_not_called()
        assert qa_client.chat.call_count == 1
        assert slack_client.send_answer.call_args.kwargs["answer"] == "기록에 있어요"

    def test_other_statuses_and_failures_do_not_search(self):
        for result in (
            None,
            "예전 문자열 답변",
            ChatResult(answer="", status="no_search_needed"),
            ChatResult(answer="", status="conflicting_evidence"),
        ):
            sut, _, qa_client, web = _make()
            qa_client.chat.return_value = result

            sut.handle_mention()

            web.search.assert_not_called()
            assert qa_client.chat.call_count == 1

    def test_without_web_search_client_behaves_as_before(self):
        sut, slack_client, qa_client, _ = _make(web=False)
        qa_client.chat.return_value = NOT_FOUND

        sut.handle_mention()

        qa_client.generate.assert_not_called()
        assert qa_client.chat.call_count == 1
        assert (
            slack_client.send_answer.call_args.kwargs["answer"]
            == "흐음~ 관련 기록에서는 확인하지 못했어요."
        )

    def test_llm_can_decline_search_for_community_only_question(self):
        sut, slack_client, qa_client, web = _make("<@U01BN035Y6L> q) 다음 빅챗 언제야?")
        qa_client.chat.return_value = NOT_FOUND
        qa_client.generate.return_value = "NONE"

        sut.handle_mention()

        web.search.assert_not_called()
        assert qa_client.chat.call_count == 1
        assert (
            slack_client.send_answer.call_args.kwargs["answer"]
            == "흐음~ 관련 기록에서는 확인하지 못했어요."
        )

    def test_query_decision_failure_falls_back_to_raw_question(self):
        sut, _, qa_client, web = _make()
        qa_client.chat.side_effect = [NOT_FOUND, ChatResult(answer="답")]
        qa_client.generate.return_value = None
        web.search.return_value = [WEB_HIT]

        sut.handle_mention()

        web.search.assert_called_once_with("re:Invent 2026 언제야?")

    def test_empty_search_results_keep_first_answer(self):
        sut, slack_client, qa_client, web = _make()
        qa_client.chat.return_value = NOT_FOUND
        qa_client.generate.return_value = "검색어"
        web.search.return_value = []

        sut.handle_mention()

        assert qa_client.chat.call_count == 1
        assert (
            slack_client.send_answer.call_args.kwargs["answer"]
            == "흐음~ 관련 기록에서는 확인하지 못했어요."
        )

    def test_search_exception_does_not_break_answer(self):
        sut, slack_client, qa_client, web = _make()
        qa_client.chat.return_value = NOT_FOUND
        qa_client.generate.return_value = "검색어"
        web.search.side_effect = RuntimeError("boom")

        assert sut.handle_mention() is True

        assert qa_client.chat.call_count == 1
        slack_client.send_answer.assert_called_once()

    def test_still_unanswered_after_web_search_says_so(self):
        sut, slack_client, qa_client, web = _make()
        qa_client.chat.side_effect = [NOT_FOUND, NOT_FOUND]
        qa_client.generate.return_value = "검색어"
        web.search.return_value = [WEB_HIT]

        sut.handle_mention()

        sent = slack_client.send_answer.call_args.kwargs
        assert sent["answer"] == "흐음~ 관련 기록과 웹에서도 확인하지 못했어요."
        assert sent["sources"] == []

    def test_thread_context_is_passed_to_query_decision(self):
        replies = [
            {"ts": "1", "user": "U1", "text": "re:Invent 올해 키노트 누구야?"},
            {"ts": "2", "user": "U2", "text": "몰라 ㅋㅋ"},
        ]
        sut, _, qa_client, web = _make(
            "<@U01BN035Y6L> q) 그거 언제야?", replies=replies
        )
        sut.thread_ts = "1"
        qa_client.chat.side_effect = [NOT_FOUND, ChatResult(answer="답")]
        qa_client.generate.return_value = "re:Invent 2026 키노트 일정"
        web.search.return_value = [WEB_HIT]

        sut.handle_mention()

        content = qa_client.generate.call_args.kwargs["content"]
        assert "앞선 대화:" in content
        assert "U1: re:Invent 올해 키노트 누구야?" in content
        assert content.endswith("질문: 그거 언제야?")


class TestWebSourceRendering(unittest.TestCase):
    def test_only_web_pages_linked_in_answer_become_sources(self):
        other = WebSearchResult(title="무관", url="https://other.test/", content="")
        result = ChatResult(
            answer="[re:Invent 2026](https://reinvent.awsevents.com/) 참고. https://unknown.test/x 도 봐."
        )

        answer, sources = QuestionResponse._render_parts(result, [WEB_HIT, other])

        assert "https://reinvent.awsevents.com/" in answer
        assert f"{UNTRUSTED_LINK_MARKER}" in answer and "unknown.test" not in answer
        assert sources == ["<https://reinvent.awsevents.com/|re:Invent 2026 · 웹>"]

    def test_community_sources_come_before_web_sources(self):
        result = ChatResult(
            answer="기록도 있고 https://reinvent.awsevents.com/ 도 있어",
            citations=["doc-1"],
            sources=[Source(document_id="doc-1", title="#공지", url="https://example.test/1")],
        )

        _, sources = QuestionResponse._render_parts(result, [WEB_HIT])

        assert sources == [
            "<https://example.test/1|#공지>",
            "<https://reinvent.awsevents.com/|re:Invent 2026 · 웹>",
        ]

    def test_render_result_appends_web_source_line(self):
        rendered = QuestionResponse._render_result(
            ChatResult(answer="https://reinvent.awsevents.com/"), [WEB_HIT]
        )

        assert rendered.endswith("출처: <https://reinvent.awsevents.com/|re:Invent 2026 · 웹>")


class TestParseWebQuery(unittest.TestCase):
    def test_takes_first_meaningful_line_without_quotes_or_prefix(self):
        assert _parse_web_query('\n"검색어: AWS re:Invent 2026"\n설명') == "AWS re:Invent 2026"
        assert _parse_web_query("`re:Invent 2026 dates`") == "re:Invent 2026 dates"

    def test_none_and_blank_mean_no_search(self):
        assert _parse_web_query("NONE") == ""
        assert _parse_web_query("none\n") == ""
        assert _parse_web_query("") == ""
        assert _parse_web_query(None) == ""

    def test_query_is_bounded(self):
        assert len(_parse_web_query("x" * 500)) == 200
