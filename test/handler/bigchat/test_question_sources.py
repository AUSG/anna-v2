from handler.bigchat.question_response import QuestionResponse
from implementation.qa_client import ChatResult, Source


def test_render_result_includes_only_cited_sources_with_title_and_time():
    result = ChatResult(
        answer="답변",
        citations=["doc-2"],
        sources=[
            Source(document_id="doc-1", title="#무관", url="https://example.test/1"),
            Source(
                document_id="doc-2",
                title="#공지",
                url="https://example.test/2",
                timestamp="2026-09-12",
            ),
        ],
    )

    rendered = QuestionResponse._render_result(result)

    assert "https://example.test/2|#공지 · 2026-09-12" in rendered
    assert "example.test/1" not in rendered


def test_render_legacy_answer_does_not_claim_sources_are_cited():
    result = ChatResult(
        answer="답변",
        sources=[Source(document_id="doc-1", title="#공지", url="https://example.test/1")],
    )

    assert QuestionResponse._render_result(result) == "답변"


def test_render_service_failure_is_distinct_from_unknown_answer():
    assert "서버" in QuestionResponse._render_result(None)
    assert "잘 모르는" in QuestionResponse._render_result(ChatResult(answer=""))


def test_render_escapes_title_rejects_unsafe_url_and_formats_timestamp_in_kst():
    result = ChatResult(
        answer="답변",
        citations=["safe", "unsafe", "bad-scheme"],
        sources=[
            Source(
                document_id="safe",
                title="A&B <공지>",
                url="https://example.test/a",
                timestamp="2026-09-12T00:00:00Z",
            ),
            Source(document_id="unsafe", title="악성", url="https://example.test/a|bad"),
            Source(document_id="bad-scheme", title="스크립트", url="javascript:alert(1)"),
        ],
    )

    rendered = QuestionResponse._render_result(result)

    assert "<https://example.test/a|A&amp;B &lt;공지&gt; · 2026-09-12 09:00 KST>" in rendered
    assert "a|bad" not in rendered
    assert "javascript:" not in rendered
