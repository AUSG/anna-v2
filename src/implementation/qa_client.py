import logging
from typing import Any, Dict, List, Optional

import requests

from application.question import (
    MAX_CONVERSATION_AUTHOR_CHARS as MAX_CONVERSATION_AUTHOR_CHARS,
    MAX_CONVERSATION_CHARS as MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGE_CHARS as MAX_CONVERSATION_MESSAGE_CHARS,
    MAX_CONVERSATION_MESSAGES as MAX_CONVERSATION_MESSAGES,
    MAX_CONVERSATION_TIMESTAMP_CHARS as MAX_CONVERSATION_TIMESTAMP_CHARS,
    ChatResult as ChatResult,
    Source as Source,
)

logger = logging.getLogger(__name__)


class QAClient:
    def __init__(self, qa_server_base_url: str, api_key: str, timeout: int = 120):
        self.qa_server_base_url = qa_server_base_url.rstrip("/")
        self.api_key = api_key
        self.namespace = "default"
        self.timeout = timeout

    def chat(
        self,
        question: str,
        system_prompt: Optional[str] = None,
        conversation: Optional[List[Dict[str, str]]] = None,
    ) -> Optional[ChatResult]:
        payload = {
            "question": question,
            "namespace": self.namespace,
            "top_k": 4,
        }

        if system_prompt:
            payload["system_prompt"] = system_prompt
        if conversation is not None:
            payload["conversation"] = _bound_conversation(conversation)

        headers = {"X-API-Key": self.api_key}

        try:
            response = requests.post(
                f"{self.qa_server_base_url}/api/v1/chat",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return self._parse_chat_response(response.json())
        except requests.exceptions.RequestException as e:
            logger.error(f"QA server request failed: {e}")
            return None
        except (TypeError, ValueError) as e:
            logger.error(f"QA server response parsing failed: {e}")
            return None

    @staticmethod
    def _parse_chat_response(data: Any) -> Optional[ChatResult]:
        """응답을 파싱하고 answer가 문자열인지 검사한다."""
        if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
            raise ValueError("chat response must contain a string answer")

        sources: List[Source] = []
        raw_sources = data.get("sources", [])
        if isinstance(raw_sources, list):
            for raw_source in raw_sources:
                if not isinstance(raw_source, dict) or not isinstance(
                    raw_source.get("document_id"), str
                ):
                    continue
                sources.append(
                    Source(
                        document_id=raw_source["document_id"],
                        score=_as_float(raw_source.get("score")),
                        title=_as_string(raw_source.get("title")),
                        url=_as_string(raw_source.get("url")),
                        evidence_urls=[
                            url
                            for url in raw_source.get("evidence_urls", [])
                            if isinstance(url, str)
                        ]
                        if isinstance(raw_source.get("evidence_urls"), list)
                        else [],
                        content_preview=_as_string(raw_source.get("content_preview")),
                        channel_id=_as_optional_string(raw_source.get("channel_id")),
                        thread_ts=_as_optional_string(raw_source.get("thread_ts")),
                        user_id=_as_optional_string(raw_source.get("user_id")),
                        timestamp=_as_optional_string(raw_source.get("timestamp")),
                        truncated=raw_source.get("truncated") is True,
                    )
                )

        raw_timing = data.get("timing", {})
        timing = dict(raw_timing) if isinstance(raw_timing, dict) else {}
        raw_citations = data.get("citations", [])
        citations = (
            [citation for citation in raw_citations if isinstance(citation, str)]
            if isinstance(raw_citations, list)
            else []
        )
        status = data.get("status", "answered")
        if not isinstance(status, str) or status not in {
            "answered",
            "insufficient_evidence",
            "no_search_needed",
            "conflicting_evidence",
        }:
            status = "answered"
        trace_id = data.get("trace_id", "")
        return ChatResult(
            answer=data["answer"],
            sources=sources,
            timing=timing,
            status=status,
            citations=citations,
            trace_id=trace_id if isinstance(trace_id, str) else "",
        )

    def generate(
        self,
        content: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        images: Optional[List[str]] = None,
    ) -> Optional[str]:
        """검색 없이 답변을 생성한다. images는 비전 입력용 data URL 목록이다."""
        payload = {"content": content, "max_tokens": max_tokens}
        if system_prompt:
            payload["system_prompt"] = system_prompt
        if images:
            payload["images"] = images

        headers = {"X-API-Key": self.api_key}

        try:
            response = requests.post(
                f"{self.qa_server_base_url}/api/v1/generate",
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["answer"]
        except requests.exceptions.RequestException as e:
            logger.error(f"QA server generate failed: {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"QA server generate parsing failed: {e}")
            return None

    def daily_digest(self) -> str:
        """어제의 다이제스트를 받는다. 실패는 호출자에게 전달한다."""
        response = requests.post(
            f"{self.qa_server_base_url}/api/v1/digest/daily",
            json={},
            headers={"X-API-Key": self.api_key},
            timeout=300,
        )
        response.raise_for_status()
        return response.json().get("text") or ""

    def is_healthy(self) -> bool:
        headers = {"X-API-Key": self.api_key}

        try:
            response = requests.get(
                f"{self.qa_server_base_url}/api/v1/chat/health",
                headers=headers,
                timeout=5,
            )
            if response.status_code == 200:
                data = response.json()
                return data.get("overall") == "healthy"
            return False
        except requests.exceptions.RequestException:
            return False


def _as_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_optional_string(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _bound_conversation(conversation: Any) -> List[Dict[str, str]]:
    """대화 입력을 API 개수와 길이 제한에 맞춘다."""
    if not isinstance(conversation, list):
        return []
    bounded: List[Dict[str, str]] = []
    total_chars = 0
    for item in conversation[:MAX_CONVERSATION_MESSAGES]:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content:
            continue
        content = content[:MAX_CONVERSATION_MESSAGE_CHARS]
        if total_chars + len(content) > MAX_CONVERSATION_CHARS:
            break
        normalized = {"role": item["role"], "content": content}
        for key, max_chars in (
            ("author", MAX_CONVERSATION_AUTHOR_CHARS),
            ("timestamp", MAX_CONVERSATION_TIMESTAMP_CHARS),
        ):
            value = item.get(key)
            if isinstance(value, str) and value:
                normalized[key] = value[:max_chars]
        bounded.append(normalized)
        total_chars += len(content)
    return bounded
