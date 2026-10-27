from typing import List, Optional, Union, get_type_hints
from unittest.mock import MagicMock, patch

import pytest
import requests

from features.questions.models import ChatFailure, ChatResult, Source, Utterance
from integrations.qa import QAClient, bound_conversation, parse_chat_response


def test_chat_contract_uses_question_models():
    assert get_type_hints(QAClient.chat) == {
        "question": str,
        "system_prompt": Optional[str],
        "conversation": Optional[List[Utterance]],
        "return": Union[ChatResult, ChatFailure],
    }
    assert get_type_hints(parse_chat_response)["return"] == ChatResult


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
    with patch("integrations.qa.requests.post", return_value=response) as post:
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert post.call_args.args[0] == "https://qa.test/api/v1/chat"
    assert post.call_args.kwargs["headers"] == {"X-API-Key": "secret"}
    assert isinstance(result, ChatResult)
    assert result.answer == "확인했어요"
    assert result.citations == ["doc-1"]
    assert result.trace_id == "trace-123"
    assert result.timing == {"search_ms": 2.5}
    assert type(result.sources[0]) is Source
    assert result.sources[0].title == "#공지"
    assert result.sources[0].timestamp == "2026-09-12T00:00:00Z"
    assert result.sources[0].truncated is True
    assert result.sources[0].evidence_urls == ["https://example.test/evidence"]


def test_source_evidence_urls_default_and_malformed_value_is_ignored():
    result = parse_chat_response(
        {"answer": "답변", "sources": [{"document_id": "doc-1", "evidence_urls": "bad"}]}
    )
    assert result.sources[0].evidence_urls == []


def test_parse_drops_sources_without_document_id_and_coerces_fields():
    result = parse_chat_response(
        {
            "answer": "답변",
            "sources": [
                "not a dict",
                {"title": "no id"},
                {"document_id": "doc-1", "score": "0.5", "title": 3, "channel_id": ""},
            ],
            "citations": "bad",
            "timing": "bad",
            "trace_id": 7,
        }
    )
    assert len(result.sources) == 1
    assert result.sources[0].score == 0.5
    assert result.sources[0].title == ""
    assert result.sources[0].channel_id is None
    assert result.citations == []
    assert result.timing == {}
    assert result.trace_id == ""


@pytest.mark.parametrize("payload", [None, [], "답변", {}, {"answer": 42}])
def test_parse_requires_a_string_answer(payload):
    with pytest.raises(ValueError):
        parse_chat_response(payload)


def test_chat_accepts_answer_only_response():
    response = _response({"answer": "예전 답변"})
    with patch("integrations.qa.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert isinstance(result, ChatResult)
    assert result.answer == "예전 답변"
    assert result.sources == []
    assert result.citations == []
    assert result.status == "answered"


def test_chat_malformed_json_is_a_failure_without_raising():
    response = _response(None)
    with patch("integrations.qa.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert isinstance(result, ChatFailure)
    assert "invalid response" in result.reason


def test_chat_malformed_status_is_treated_as_answered():
    response = _response({"answer": "답변", "status": []})
    with patch("integrations.qa.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert result.status == "answered"


def test_chat_known_status_is_kept():
    response = _response({"answer": "답변", "status": "insufficient_evidence"})
    with patch("integrations.qa.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert result.status == "insufficient_evidence"


def test_chat_http_error_is_service_failure_and_not_insufficient_evidence():
    response = MagicMock()
    response.raise_for_status.side_effect = requests.HTTPError("503")
    with patch("integrations.qa.requests.post", return_value=response):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert isinstance(result, ChatFailure)
    assert "request failed" in result.reason


def test_chat_connection_error_is_a_failure():
    with patch(
        "integrations.qa.requests.post",
        side_effect=requests.exceptions.ConnectTimeout(),
    ):
        result = QAClient("https://qa.test", "secret").chat("질문")

    assert isinstance(result, ChatFailure)


def test_chat_sends_system_prompt_and_conversation_separately_and_bounds_it():
    response = _response({"answer": "답변"})
    conversation = [
        Utterance(role="user", content="u" * 5000, author="U1" * 200),
        Utterance(role="assistant", content="a", timestamp="123" * 100),
        Utterance(role="system", content="should be dropped"),
    ]
    with patch("integrations.qa.requests.post", return_value=response) as post:
        QAClient("https://qa.test", "secret").chat(
            "현재 질문", system_prompt="친절하게", conversation=conversation
        )

    payload = post.call_args.kwargs["json"]
    assert payload["question"] == "현재 질문"
    assert payload["system_prompt"] == "친절하게"
    assert payload["conversation"] == [
        {"role": "user", "content": "u" * 4000, "author": "U1" * 100},
        {"role": "assistant", "content": "a", "timestamp": "123" * 33 + "1"},
    ]


def test_chat_omits_conversation_and_system_prompt_when_not_given():
    response = _response({"answer": "답변"})
    with patch("integrations.qa.requests.post", return_value=response) as post:
        QAClient("https://qa.test", "secret").chat("질문")

    payload = post.call_args.kwargs["json"]
    assert "conversation" not in payload
    assert "system_prompt" not in payload


def test_bound_conversation_drops_empty_and_unknown_roles():
    bounded = bound_conversation(
        [
            Utterance(role="user", content=""),
            Utterance(role="system", content="x"),
            Utterance(role="assistant", content="ok"),
        ]
    )
    assert bounded == [{"role": "assistant", "content": "ok"}]


def test_bound_conversation_caps_message_count_and_total_chars():
    many = [Utterance(role="user", content="m") for _ in range(150)]
    assert len(bound_conversation(many)) == 100

    big = [Utterance(role="user", content="x" * 4000) for _ in range(11)]
    bounded = bound_conversation(big)
    assert len(bounded) == 10  # 40000 자까지만
    assert sum(len(u["content"]) for u in bounded) == 40000


def test_daily_digest_returns_text_and_raises_on_http_error():
    with patch(
        "integrations.qa.requests.post",
        return_value=_response({"text": "핫스레드"}),
    ) as post:
        assert QAClient("https://qa.test/", "secret").daily_digest() == "핫스레드"
    assert post.call_args.args[0] == "https://qa.test/api/v1/digest/daily"

    failed = _response({}, status_code=503)
    failed.raise_for_status.side_effect = requests.exceptions.HTTPError("503")
    with patch("integrations.qa.requests.post", return_value=failed):
        with pytest.raises(requests.exceptions.HTTPError):
            QAClient("https://qa.test", "secret").daily_digest()


def test_daily_digest_returns_empty_string_when_text_is_missing():
    with patch("integrations.qa.requests.post", return_value=_response({})):
        assert QAClient("https://qa.test", "secret").daily_digest() == ""
