from handler.bigchat.question_response import QuestionResponse, UNTRUSTED_LINK_MARKER
from implementation.qa_client import ChatResult, Source
from unittest.mock import MagicMock


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


def test_render_distinguishes_insufficient_evidence_from_service_failure():
    assert QuestionResponse._render_result(
        ChatResult(answer="", status="insufficient_evidence")
    ) == "흐음~ 관련 기록에서는 확인하지 못했어요."
    assert "서버" in QuestionResponse._render_result(None)


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


def test_render_strips_untrusted_links_from_model_answer_but_keeps_cited_url():
    result = ChatResult(
        answer=(
            "공식 문서는 <https://example.test/doc|여기>에 있고, "
            "추가 정보는 [악성 링크](https://evil.test/phish) 또는 "
            "https://evil.test/plain 을 보세요."
        ),
        citations=["doc-1"],
        sources=[Source(document_id="doc-1", url="https://example.test/doc")],
    )

    rendered = QuestionResponse._render_result(result)

    assert "<https://example.test/doc|여기>" in rendered
    assert "evil.test" not in rendered


def test_render_preserves_allowed_markdown_url_and_punctuation():
    result = ChatResult(
        answer="문서는 [여기](https://example.test/doc), 에서 확인하세요.",
        citations=["doc-1"],
        sources=[Source(document_id="doc-1", url="https://example.test/doc")],
    )

    rendered = QuestionResponse._render_result(result)

    assert "[여기](https://example.test/doc)," in rendered
    assert UNTRUSTED_LINK_MARKER not in rendered


def test_render_marks_malformed_and_plain_untrusted_links_and_legacy_strings():
    result = ChatResult(
        answer="깨진 <https://evil.test/no-close|링크\n일반 https://evil.test/plain.",
        citations=[],
    )

    rendered = QuestionResponse._render_result(result)

    assert "evil.test" not in rendered
    assert rendered.count(UNTRUSTED_LINK_MARKER) == 2
    assert rendered.endswith(".")
    assert UNTRUSTED_LINK_MARKER in QuestionResponse._render_result(
        "예전 답변 https://evil.test/plain"
    )


def test_render_omits_ambiguous_duplicate_document_ids():
    result = ChatResult(
        answer="답변",
        citations=["same"],
        sources=[
            Source(document_id="same", title="#첫번째", url="https://example.test/1"),
            Source(document_id="same", title="#두번째", url="https://example.test/2"),
        ],
    )

    rendered = QuestionResponse._render_result(result)

    assert rendered == "답변"


def test_handler_keeps_current_question_separate_and_preserves_identities():
    event = {
        "text": "<@UANNA> q) 지금 뭐야?",
        "ts": "3",
        "channel": "C1",
        "thread_ts": "1",
        "user": "U2",
    }
    slack = MagicMock()
    slack.get_replies.return_value = [
        MagicMock(ts="1", user="U1", text="원래 질문"),
        MagicMock(ts="2", user="UANNA", text="제가 답했어요", bot_id="B1"),
        MagicMock(ts="3", user="U2", text="<@UANNA> q) 지금 뭐야?"),
    ]
    qa = MagicMock()
    qa.chat.return_value = "답변"

    handler = QuestionResponse(event, slack, qa, assistant_id="UANNA")
    handler.handle_mention()

    assert qa.chat.call_args.kwargs["question"] == "지금 뭐야?"
    assert qa.chat.call_args.kwargs["conversation"] == [
        {"role": "user", "content": "원래 질문", "author": "U1", "timestamp": "1"},
        {"role": "assistant", "content": "제가 답했어요", "author": "UANNA", "timestamp": "2"},
    ]


def test_handler_bounds_history_to_root_and_recent_turns():
    event = {"text": "<@UANNA> q) 질문", "ts": "99", "channel": "C1", "thread_ts": "1"}
    slack = MagicMock()
    slack.get_replies.return_value = [
        MagicMock(ts=str(i), user=f"U{i}", text=f"메시지-{i}" * 2000) for i in range(50)
    ]
    qa = MagicMock()
    qa.chat.return_value = "답변"

    QuestionResponse(event, slack, qa).handle_mention()
    conversation = qa.chat.call_args.kwargs["conversation"]

    assert len(conversation) <= 40
    assert sum(len(item["content"]) for item in conversation) <= 16000
    assert conversation[0]["content"].startswith("메시지-0")
    assert conversation[-1]["content"].startswith("메시지-49")


def test_handler_prioritizes_a_relevant_middle_turn_before_filler():
    event = {"text": "<@UANNA> q) Kubernetes 일정", "ts": "99", "channel": "C1", "thread_ts": "1"}
    slack = MagicMock()
    messages = [MagicMock(ts=str(i), user=f"U{i}", text=f"무관한 메시지 {i}" * 1000) for i in range(20)]
    messages[10] = MagicMock(ts="10", user="U10", text="Kubernetes 일정은 10월이에요" * 1000)
    slack.get_replies.return_value = messages
    qa = MagicMock()
    qa.chat.return_value = "답변"

    QuestionResponse(event, slack, qa).handle_mention()
    conversation = qa.chat.call_args.kwargs["conversation"]

    assert any("Kubernetes" in item["content"] for item in conversation)
