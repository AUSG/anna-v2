"""클라이언트 생성이나 API 호출 없이 멘션 명령을 판별한다."""

import re
from typing import Literal

MentionCommand = Literal[
    "explicit_question",
    "shuffle",
    "reminder",
    "create_bigchat",
    "create_issue",
    "help",
    "question",
    "empty",
]

REMINDER_TRIGGER = "빅챗 리마인더"
# '만들어줘'/'만들자' 같은 어미까지 포함해야 트리거 뒤에 제목만 남는다.
ISSUE_TRIGGER_PATTERN = re.compile(
    r"(?:새로운\s*이슈|새\s*이슈|이슈\s*(?:만들|만드|등록|생성)[가-힣]*|이슈\s*(?:파|따)(?:줘|자|줄래|주라|주세요))"
)
MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")
QUESTION_PATTERN = re.compile(r"q\)\s*(.+)", re.IGNORECASE | re.DOTALL)


def extract_question(text: str, require_prefix: bool = True) -> str:
    clean_text = MENTION_PATTERN.sub("", text).strip()
    match = QUESTION_PATTERN.search(clean_text)
    if match:
        return match.group(1).strip()
    return "" if require_prefix else clean_text


def matches_mention(command: MentionCommand, text: str) -> bool:
    """라우터와 개별 핸들러가 같은 판별 조건을 사용한다."""
    match command:
        case "explicit_question":
            return "q)" in text.lower()
        case "shuffle":
            return "섞어줘" in text or "shuffle" in text.lower()
        case "reminder":
            return REMINDER_TRIGGER in text
        case "create_bigchat":
            return "새로운 빅챗" in text
        case "create_issue":
            return bool(ISSUE_TRIGGER_PATTERN.search(text))
        case "help":
            return "help" in text or "도움" in text
        case "question":
            return bool(extract_question(text, require_prefix=False))
        case "empty":
            return not extract_question(text, require_prefix=False)
        case _:
            raise ValueError(f"Unknown mention command: {command}")


def classify_mention(text: str) -> MentionCommand:
    # 기존 우선순위 유지: 명시적 질문이 명령보다 먼저, 일반 질문은 명령보다 나중.
    commands: tuple[MentionCommand, ...] = (
        "explicit_question",
        "shuffle",
        "reminder",
        "create_bigchat",
        "create_issue",
        "help",
        "question",
    )
    for command in commands:
        if matches_mention(command, text):
            return command
    return "empty"
