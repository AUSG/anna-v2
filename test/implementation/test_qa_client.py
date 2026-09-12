from unittest.mock import MagicMock, patch

import requests

from implementation.qa_client import ChatResult, QAClient


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_chat_parses_structured_result_and_source_metadata():
    response = _response(
        {
            "answer": "확인했어요",
            "status": "answered",
            "citations": ["doc-1"],
            "trace_id": "trace-123",
            "sources": [
                {
                    "document_id": "doc-1",
                    "title": "#공지",
                    "url": "https://example.test/doc-1",
                    "evidence_urls": ["https://example.test/evidence", 42],
                    "timestamp": "2026-09-12T00:00:00Z",
                    "truncated": True,
                }
            ],
            "timing": {"search_ms": 2.5},
        }
    )
    with patch("implementation.qa_client.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert isinstance(result, ChatResult)
    assert result.answer == "확인했어요"
    assert result.citations == ["doc-1"]
    assert result.trace_id == "trace-123"
    assert result.sources[0].timestamp == "2026-09-12T00:00:00Z"
    assert result.sources[0].truncated is True
    assert result.sources[0].evidence_urls == ["https://example.test/evidence"]


def test_source_evidence_urls_default_and_malformed_value_is_ignored():
    result = QAClient._parse_chat_response(
        {"answer": "답변", "sources": [{"document_id": "doc-1", "evidence_urls": "bad"}]}
    )
    assert result.sources[0].evidence_urls == []


def test_chat_accepts_legacy_answer_only_response():
    response = _response({"answer": "예전 답변"})
    with patch("implementation.qa_client.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert result.answer == "예전 답변"
    assert result.sources == []
    assert result.citations == []


def test_chat_malformed_json_returns_none_without_raising():
    response = _response(None)
    with patch("implementation.qa_client.requests.post", return_value=response):
        assert QAClient("https://qa.test", "secret").chat("질문") is None


def test_chat_malformed_status_is_treated_as_answered():
    response = _response({"answer": "답변", "status": []})
    with patch("implementation.qa_client.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert result.status == "answered"

def test_chat_http_error_is_service_failure_and_not_insufficient_evidence():
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("503")
    with patch("implementation.qa_client.requests.post", return_value=response):
        assert QAClient("https://qa.test", "secret").chat("질문") is None


def test_chat_sends_conversation_separately_and_bounds_it():
    response = _response({"answer": "답변"})
    conversation = [
        {"role": "user", "content": "u" * 5000, "author": "U1" * 200},
        {"role": "assistant", "content": "a", "timestamp": "123" * 100},
        {"role": "system", "content": "should be dropped"},
    ]
    with patch("implementation.qa_client.requests.post", return_value=response) as post:
        QAClient("https://qa.test", "secret").chat("현재 질문", conversation=conversation)

    payload = post.call_args.kwargs["json"]
    assert payload["question"] == "현재 질문"
    assert payload["conversation"] == [
        {"role": "user", "content": "u" * 4000, "author": "U1" * 100},
        {"role": "assistant", "content": "a", "timestamp": "123" * 33 + "1"},
    ]
