"""Select bounded conversation turns from normalized text and metadata."""

import re
from typing import Dict, List

from implementation.qa_client import MAX_CONVERSATION_CHARS, MAX_CONVERSATION_MESSAGES


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
