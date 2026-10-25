"""QA response values and bounded conversation selection."""

import re
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
    evidence_urls: List[str] = field(default_factory=list)


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


def select_conversation(
    normalized: List[Dict[str, str]], question: str
) -> List[Dict[str, str]]:
    """Keep selected objects in input order without copying or mutating them."""
    if not normalized:
        return []

    # Keep the root, turns matching the current question, and newest turns.
    # This retains both the topic and a useful middle reference when a long
    # thread would otherwise leave only the most recent messages.
    root = normalized[0]
    terms = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", question.lower()))
    relevant = [
        item
        for item in normalized[1:]
        if any(term in item["content"].lower() for term in terms)
    ]
    recent = list(reversed(normalized[1:]))
    candidates = [root] + relevant + recent
    kept, total = [], 0
    for item in candidates:
        content = item["content"]
        if (
            len(kept) >= MAX_CONVERSATION_MESSAGES
            or total + len(content) > MAX_CONVERSATION_CHARS
        ):
            continue
        kept.append(item)
        total += len(content)
    kept_ids = {id(item) for item in kept}
    return [item for item in normalized if id(item) in kept_ids]
