import pytest

from features.questions.models import ChatResult, Source
from features.questions.presentation.answers import (
    _format_timestamp,
    _safe_source_url,
    render_parts,
)

_GITHUB_URL = "https://github.com/AUSG/anna-v2"
_WIKI_URL = "https://example.test/wiki/Foo_(bar)"
_DOC_LINK = "<https://example.test/doc|doc-1>"
_UNKNOWN_ANSWER = "흐음~ 나도 잘 모르는 일인걸? 오거나이저를 찾아볼까?"


@pytest.mark.parametrize(
    ("result", "answer", "sources"),
    [
        pytest.param(
            ChatResult(
                answer="답변",
                citations=["doc-2"],
                sources=[
                    Source(
                        document_id="doc-1", title="#무관", url="https://example.test/1"
                    ),
                    Source(
                        document_id="doc-2",
                        title="#공지",
                        url="https://example.test/2",
                        timestamp="2026-09-12",
                    ),
                ],
            ),
            "답변",
            ["<https://example.test/2|#공지 · 2026-09-12 09:00 KST>"],
            id="cited-title-date",
        ),
        pytest.param(
            ChatResult(
                answer="답변",
                sources=[
                    Source(
                        document_id="doc-1", title="#공지", url="https://example.test/1"
                    )
                ],
            ),
            "답변",
            [],
            id="uncited-only",
        ),
        pytest.param(
            ChatResult(
                answer="답변",
                citations=["safe", "unsafe", "bad-scheme"],
                sources=[
                    Source(
                        document_id="safe",
                        title="A&B <공지>",
                        url="https://example.test/a",
                        timestamp="2026-09-12T00:00:00Z",
                    ),
                    Source(
                        document_id="unsafe",
                        title="악성",
                        url="https://example.test/a|bad",
                    ),
                    Source(
                        document_id="bad-scheme",
                        title="스크립트",
                        url="javascript:alert(1)",
                    ),
                ],
            ),
            "답변",
            ["<https://example.test/a|A&amp;B &lt;공지&gt; · 2026-09-12 09:00 KST>"],
            id="unsafe-source-utc",
        ),
        pytest.param(
            ChatResult(
                answer=(
                    "공식 문서는 <https://example.test/doc|여기>에 있고, "
                    "추가 정보는 [악성 링크](https://evil.test/phish) 또는 "
                    "https://evil.test/plain 을 보세요."
                ),
                citations=["doc-1"],
                sources=[Source(document_id="doc-1", url="https://example.test/doc")],
            ),
            "공식 문서는 <https://example.test/doc|여기>에 있고, "
            "추가 정보는 악성 링크[확인되지 않은 링크 제거] 또는 "
            "[확인되지 않은 링크 제거] 을 보세요.",
            [_DOC_LINK],
            id="trusted-slack-untrusted-links",
        ),
        pytest.param(
            ChatResult(
                answer="문서는 [여기](https://example.test/doc), 에서 확인하세요.",
                citations=["doc-1"],
                sources=[Source(document_id="doc-1", url="https://example.test/doc")],
            ),
            "문서는 [여기](https://example.test/doc), 에서 확인하세요.",
            [_DOC_LINK],
            id="trusted-markdown-comma",
        ),
        pytest.param(
            ChatResult(
                answer=f"`{_GITHUB_URL}`예요. [문서]({_WIKI_URL})",
                citations=["doc-1"],
                sources=[
                    Source(
                        document_id="doc-1",
                        url="https://example.test/doc",
                        evidence_urls=[_GITHUB_URL, _WIKI_URL],
                    )
                ],
            ),
            "`https://github.com/AUSG/anna-v2`예요. [문서](https://example.test/wiki/Foo_(bar))",
            [_DOC_LINK],
            id="evidence-backtick-balanced",
        ),
        pytest.param(
            ChatResult(
                answer="[알 수 없음](https://evil.test/no) [미인용](https://example.test/evidence)",
                citations=[],
                sources=[
                    Source(
                        document_id="doc-1",
                        url="https://example.test/doc",
                        evidence_urls=["https://example.test/evidence"],
                    )
                ],
            ),
            "알 수 없음[확인되지 않은 링크 제거] 미인용[확인되지 않은 링크 제거]",
            [],
            id="unknown-uncited-evidence",
        ),
        pytest.param(
            ChatResult(
                answer="대화에서 확인했어요.",
                citations=["conversation:current"],
                sources=[
                    Source(
                        document_id="conversation:current",
                        url="conversation:current",
                        title="현재 대화",
                    )
                ],
            ),
            "대화에서 확인했어요.",
            ["현재 대화"],
            id="synthetic-only",
        ),
        pytest.param(
            ChatResult(
                answer="깨진 <https://evil.test/no-close|링크\n일반 https://evil.test/plain.",
                citations=[],
            ),
            "깨진 링크[확인되지 않은 링크 제거]\n일반 [확인되지 않은 링크 제거].",
            [],
            id="malformed-structured",
        ),
        pytest.param(
            "예전 답변 https://evil.test/plain",
            "예전 답변 [확인되지 않은 링크 제거]",
            [],
            id="legacy-untrusted-url",
        ),
        pytest.param(
            ChatResult(
                answer="답변",
                citations=["same"],
                sources=[
                    Source(
                        document_id="same", title="#첫번째", url="https://example.test/1"
                    ),
                    Source(
                        document_id="same", title="#두번째", url="https://example.test/2"
                    ),
                ],
            ),
            "답변",
            [],
            id="duplicate-only",
        ),
        pytest.param(
            "HTTPS://wrong.test www.wrong.test",
            "[확인되지 않은 링크 제거] [확인되지 않은 링크 제거]",
            [],
            id="legacy-uppercase-www",
        ),
        pytest.param(
            "<https://wrong.test|출처> [출처](https://wrong.test)",
            "출처[확인되지 않은 링크 제거] 출처[확인되지 않은 링크 제거]",
            [],
            id="legacy-named-links",
        ),
        pytest.param(
            ChatResult(
                answer="[공지](https://example.test/1)은 여기, https://example.test/1은 같은 링크.",
                citations=["doc-1"],
                sources=[
                    Source(
                        document_id="doc-1", title="#공지", url="https://example.test/1"
                    )
                ],
            ),
            "[공지](https://example.test/1)은 여기, https://example.test/1은 같은 링크.",
            ["<https://example.test/1|#공지>"],
            id="trusted-particle",
        ),
    ],
)
def test_render_parts_cases(result, answer, sources):
    assert render_parts(result) == (answer, sources)


@pytest.mark.parametrize("result", [None, {}, [], False, 42])
def test_missing_or_wrong_result_type_is_service_failure(result):
    assert render_parts(result) == (
        "앗, 답변 서버가 잠시 응답하지 않아요. 잠시 후 다시 시도해 주세요.",
        [],
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("insufficient_evidence", "흐음~ 관련 기록에서는 확인하지 못했어요."),
        ("conflicting_evidence", "흐음~ 기록이 서로 달라서 확답하기 어렵네요."),
        ("answered", _UNKNOWN_ANSWER),
        ("no_search_needed", _UNKNOWN_ANSWER),
        ("unknown", _UNKNOWN_ANSWER),
    ],
)
def test_empty_structured_answer_uses_status_fallback(status, expected):
    assert render_parts(ChatResult(answer="", status=status)) == (expected, [])


@pytest.mark.parametrize("answer", ["", " \t\n", "가\r\n나\u2028다\u2029😀e\u0301"])
def test_legacy_strings_and_structured_whitespace_remain_distinct(answer):
    assert render_parts(answer) == (answer, [])
    if answer:
        assert render_parts(ChatResult(answer=answer)) == (answer, [])


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.test/한글?x=1&y=2", "https://example.test/한글?x=1&y=2"),
        ("HTTP://example.test/Foo_(bar)", "HTTP://example.test/Foo_(bar)"),
        ("https://example.test:bad/path", "https://example.test:bad/path"),
        ("https://", ""),
        ("//example.test/a", ""),
        ("www.example.test", ""),
        ("javascript:alert(1)", ""),
        ("https://example.test/a|b", ""),
        ("https://example.test/<a>", ""),
        ("https://example.test/`a`", ""),
        ("https://example.test/a\u00a0b", ""),
        ("https://example.test/a\u2028b", ""),
        (None, ""),
        (42, ""),
    ],
)
def test_source_url_validation_is_not_replaced_by_answer_normalization(value, expected):
    assert _safe_source_url(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "1970-01-01 09:00 KST"),
        ("0.999999", "1970-01-01 09:00 KST"),
        ("2026-09-12", "2026-09-12 09:00 KST"),
        ("2026-09-12T23:30:00-02:00", "2026-09-13 10:30 KST"),
        ("2026-09-12T00:00:00", "2026-09-12 09:00 KST"),
        ("not a date\u2028가", "not a date\u2028가"),
        ("2026-02-30", "2026-02-30"),
        ("9" * 400, "9" * 400),
        (None, None),
        (42, 42),
    ],
)
def test_timestamp_conversion_and_invalid_input_fallback(value, expected):
    assert _format_timestamp(value) == expected


def test_source_order_escaping_current_source_and_ambiguous_ids_are_preserved():
    result = ChatResult(
        answer="확인했어요.",
        citations=["doc-2", None, "same", "conversation:current", "doc-1", "doc-1"],
        sources=[
            Source(document_id="doc-1", title="A&B <공지>", url="https://a.test/1"),
            Source(document_id="same", url="https://a.test/dup1"),
            Source(document_id="same", url="https://a.test/dup2"),
            Source(
                document_id="conversation:current",
                url="conversation:current",
                title="현재 <대화>",
            ),
            Source(document_id="doc-2", url="https://a.test/2", timestamp="bad&time"),
            Source(document_id="uncited", url="https://a.test/uncited"),
        ],
    )

    assert render_parts(result) == (
        "확인했어요.",
        [
            "<https://a.test/1|A&amp;B &lt;공지&gt;>",
            "현재 &lt;대화&gt;",
            "<https://a.test/2|doc-2 · bad&time>",
        ],
    )


def test_evidence_urls_require_unique_cited_source_even_without_source_permalink():
    result = ChatResult(
        answer="https://a.test/keep https://a.test/dup https://a.test/uncited",
        citations=["safe", "dup"],
        sources=[
            Source(
                document_id="safe", url="unsafe", evidence_urls=["https://a.test/keep"]
            ),
            Source(document_id="dup", evidence_urls=["https://a.test/dup"]),
            Source(document_id="dup", evidence_urls=["https://a.test/dup"]),
            Source(document_id="uncited", evidence_urls=["https://a.test/uncited"]),
        ],
    )

    assert render_parts(result) == (
        "https://a.test/keep [확인되지 않은 링크 제거] [확인되지 않은 링크 제거]",
        [],
    )
