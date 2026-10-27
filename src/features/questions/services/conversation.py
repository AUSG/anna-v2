"""프레임워크나 SDK와 독립적인 대화 구성과 선택 정책."""

import re
from typing import List, Optional

from features.questions.models import (
    MAX_CONVERSATION_AUTHOR_CHARS,
    MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGE_CHARS,
    MAX_CONVERSATION_MESSAGES,
    MAX_CONVERSATION_TIMESTAMP_CHARS,
    Utterance,
)
from shared.slack_models import Message


def normalize_conversation(
    messages: List[Message],
    *,
    current_ts: str,
    assistant_id: Optional[str],
) -> List[Utterance]:
    """스레드 메시지를 발화로 바꾸고 필드별 길이를 제한한다. 현재 멘션 글은 뺀다."""
    normalized = []
    for message in messages:
        if message.ts == current_ts:
            continue
        text = message.text.strip()
        if not text:
            continue
        # 안나 ID가 있으면 일치 여부로 발화를 구분한다. 다른 봇(GeekNews 등)은 user 가
        # 없어 bot_id 가 author 로 들어오지만, 이름이라도 남겨야 누가 쓴 글인지 안다.
        role = "assistant" if assistant_id and message.user == assistant_id else "user"
        normalized.append(
            Utterance(
                role=role,
                content=text[:MAX_CONVERSATION_MESSAGE_CHARS],
                author=message.user[:MAX_CONVERSATION_AUTHOR_CHARS],
                timestamp=message.ts[:MAX_CONVERSATION_TIMESTAMP_CHARS],
            )
        )
    return normalized


def select_conversation(normalized: List[Utterance], question: str) -> List[Utterance]:
    """첫 글, 질문 관련 글, 최근 글 순으로 고르되 입력 순서로 돌려준다."""
    if not normalized:
        return []
    root = normalized[0]
    terms = set(re.findall(r"[0-9A-Za-z가-힣]{2,}", question.lower()))
    relevant = [
        item
        for item in normalized[1:]
        if any(term in item.content.lower() for term in terms)
    ]
    recent = list(reversed(normalized[1:]))
    candidates = [root] + relevant + recent
    kept, total = [], 0
    for item in candidates:
        if any(item is k for k in kept):
            continue
        if (
            len(kept) >= MAX_CONVERSATION_MESSAGES
            or total + len(item.content) > MAX_CONVERSATION_CHARS
        ):
            continue
        kept.append(item)
        total += len(item.content)
    return [item for item in normalized if any(item is k for k in kept)]
