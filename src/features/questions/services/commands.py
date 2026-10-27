"""질문 명령 문법. 클라이언트 생성이나 API 호출 없이 입력을 해석한다."""

import re

from shared.slack_commands import MENTION_PATTERN

QUESTION_PATTERN = re.compile(r"q\)\s*(.+)", re.IGNORECASE | re.DOTALL)


def extract_question(text: str, require_prefix: bool = True) -> str:
    clean_text = MENTION_PATTERN.sub("", text).strip()
    match = QUESTION_PATTERN.search(clean_text)
    if match:
        return match.group(1).strip()
    return "" if require_prefix else clean_text
