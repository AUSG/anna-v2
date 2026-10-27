"""클라이언트 생성이나 API 호출 없이 멘션 명령을 판별한다."""

from typing import Literal

from features.bigchat.services.commands import REMINDER_TRIGGER
from features.issues.services.commands import ISSUE_TRIGGER_PATTERN
from features.questions.services.commands import extract_question


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
    # 명시적 질문, 명령, 일반 질문 순으로 판별한다.
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
