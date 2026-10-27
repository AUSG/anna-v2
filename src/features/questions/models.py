"""QA 응답 값과 서비스 공통 입력 한도."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# crawler 의 /api/v1/chat 상한(services/conversation.py)과 맞춘다
MAX_CONVERSATION_MESSAGES = 100
MAX_CONVERSATION_MESSAGE_CHARS = 4000
MAX_CONVERSATION_CHARS = 40000
MAX_CONVERSATION_AUTHOR_CHARS = 200
MAX_CONVERSATION_TIMESTAMP_CHARS = 100


@dataclass
class Source:
    """QA 응답의 출처 문서."""

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
    evidence_urls: List[str] = field(default_factory=list)


@dataclass
class ChatResult:
    """답변, 출처, 처리 상태와 추적 정보를 담는다."""

    answer: str
    sources: List[Source] = field(default_factory=list)
    timing: Dict[str, Any] = field(default_factory=dict)
    status: str = "answered"
    citations: List[str] = field(default_factory=list)
    trace_id: str = ""
