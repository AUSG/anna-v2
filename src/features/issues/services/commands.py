"""이슈 생성 명령의 입력 해석."""

import re

from features.issues.models import CreateIssue
from shared.slack_commands import strip_mentions

# '만들어줘'/'만들자' 같은 어미까지 포함해야 트리거 뒤에 제목만 남는다.
ISSUE_TRIGGER_PATTERN = re.compile(
    r"(?:새로운\s*이슈|새\s*이슈|이슈\s*(?:만들|만드|등록|생성)[가-힣]*|이슈\s*(?:파|따)(?:줘|자|줄래|주라|주세요))"
)
# 슬랙 한 줄이 그대로 제목이 되므로, 깃허브 제한(256자)보다 짧게 잘라 목록에서 읽히게 한다
MAX_TITLE_LEN = 120


def is_create_issue(text: str) -> bool:
    return bool(ISSUE_TRIGGER_PATTERN.search(text))


def parse_issue_command(text: str) -> CreateIssue:
    """트리거 뒤의 첫 줄을 제목으로, 나머지 줄을 본문으로 나눈다. 제목이 없으면 빈 제목."""
    after_trigger = ISSUE_TRIGGER_PATTERN.split(text, maxsplit=1)[-1]
    # 안나 멘션이 명령 앞뒤 어디에 있든 제목에 섞이지 않게 걷어낸다
    cleaned = strip_mentions(after_trigger)
    # "이슈 만들어줄래? 제목", "이슈 만들어줘: 제목" 처럼 어미 뒤에 남는 문장부호를 턴다
    cleaned = cleaned.lstrip("?!.,:;~ \t")
    if not cleaned:
        return CreateIssue("", "")
    title, _, body = cleaned.partition("\n")
    title = title.strip()
    if len(title) > MAX_TITLE_LEN:
        title = title[: MAX_TITLE_LEN - 1].rstrip() + "…"
    return CreateIssue(title, body.strip())
