import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


@dataclass
class Source:
    """A document returned by the QA service."""

    document_id: str
    score: float = 0.0
    title: str = ""
    url: str = ""
    content_preview: str = ""
    channel_id: Optional[str] = None
    thread_ts: Optional[str] = None
    user_id: Optional[str] = None
    timestamp: Optional[str] = None
    truncated: bool = False


@dataclass
class ChatResult:
    """Structured chat response from crawler-rag.

    ``status``, ``citations`` and ``trace_id`` were added after the original
    answer-only endpoint. Defaults keep callers compatible with old responses.
    """

    answer: str
    sources: List[Source] = field(default_factory=list)
    timing: Dict[str, Any] = field(default_factory=dict)
    status: str = "answered"
    citations: List[str] = field(default_factory=list)
    trace_id: str = ""


class QAClient:
    def __init__(self, qa_server_base_url: str, api_key: str, timeout: int = 120):
        self.qa_server_base_url = qa_server_base_url.rstrip("/")
        self.api_key = api_key
        self.namespace = "default"
        self.timeout = timeout

    def chat(self, question: str, system_prompt: Optional[str] = None) -> Optional[ChatResult]:
        payload = {
            "question": question,
            "namespace": self.namespace,
            "top_k": 4,
        }

        if system_prompt:
            payload["system_prompt"] = system_prompt

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
        """Parse current and legacy response shapes without raising on bad JSON."""
        if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
            raise ValueError("chat response must contain a string answer")

        sources: List[Source] = []
        raw_sources = data.get("sources", [])
        if isinstance(raw_sources, list):
            for raw_source in raw_sources:
                if not isinstance(raw_source, dict) or not isinstance(raw_source.get("document_id"), str):
                    continue
                sources.append(
                    Source(
                        document_id=raw_source["document_id"],
                        score=_as_float(raw_source.get("score")),
                        title=_as_string(raw_source.get("title")),
                        url=_as_string(raw_source.get("url")),
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
        """검색(RAG) 없이 순수 LLM 생성. 페르소나 기반 답글 등에 사용.

        images: 이미지 data URL 리스트 (예: "data:image/png;base64,...") — 있으면 비전 입력.
        """
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
        except (KeyError, ValueError) as e:
            logger.error(f"QA server generate parsing failed: {e}")
            return None

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
