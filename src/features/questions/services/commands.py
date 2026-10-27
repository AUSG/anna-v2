"""질문 명령 문법. 클라이언트 생성이나 API 호출 없이 입력을 해석한다."""

import re
from typing import Optional

from features.questions.models import Question
from shared.slack_commands import strip_mentions

QUESTION_PATTERN = re.compile(r"(?is)q\)\s*(.+)")


def is_explicit_question(text: str) -> bool:
    return "q)" in text.lower()


def extract_question(text: str, require_prefix: bool = True) -> str:
    clean_text = strip_mentions(text)
    match = QUESTION_PATTERN.search(clean_text)
    if match:
        return match.group(1).strip()
    return "" if require_prefix else clean_text


def parse_explicit_question(text: str) -> Question:
    return Question(extract_question(text, require_prefix=True), explicit=True)


def parse_plain_question(text: str) -> Optional[Question]:
    """명령이 아닌 멘션 본문. 비어 있으면 None."""
    body = extract_question(text, require_prefix=False)
    return Question(body, explicit=False) if body else None
