"""이슈 생성 명령의 입력 해석."""

import re

from shared.slack_commands import MENTION_PATTERN

ISSUE_TRIGGER_PATTERN = re.compile(
    r"(?:새로운\s*이슈|새\s*이슈|이슈\s*(?:만들|만드|등록|생성)[가-힣]*|이슈\s*(?:파|따)(?:줘|자|줄래|주라|주세요))"
)
MAX_TITLE_LEN = 120


def parse_issue_command(text: str) -> tuple[str, str]:
    after_trigger = ISSUE_TRIGGER_PATTERN.split(text, maxsplit=1)[-1]
    cleaned = MENTION_PATTERN.sub("", after_trigger).strip()
    cleaned = cleaned.lstrip("?!.,:;~ \t")
    if not cleaned:
        return "", ""
    title, _, body = cleaned.partition("\n")
    title = title.strip()
    if len(title) > MAX_TITLE_LEN:
        title = title[: MAX_TITLE_LEN - 1].rstrip() + "…"
    return title, body.strip()
