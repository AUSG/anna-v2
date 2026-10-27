"""빅챗 멘션 명령의 문법과 입력 해석. 외부 호출 없이 문자열만 다룬다."""

from dataclasses import dataclass
from typing import Literal, Tuple

from shared.slack_commands import SLACK_USER_PATTERN, strip_mentions

CREATE_BIGCHAT_TRIGGER = "새로운 빅챗"
REMINDER_TRIGGER = "빅챗 리마인더"
REMINDER_TEST_PHRASE = "테스트"
# 전원 발송은 이 확인 문구가 있을 때만 실행한다.
REMINDER_BROADCAST_PHRASE = "지금 전원 발송"


@dataclass(frozen=True)
class CreateBigchat:
    sheet_name: str  # 트리거 뒤 첫 줄. 형식 검증은 CreateBigchatCommand.parse 가 한다


@dataclass(frozen=True)
class Reminder:
    mode: Literal["test", "broadcast", "usage"]
    target_ids: Tuple[str, ...] = ()


def is_create_bigchat(text: str) -> bool:
    return CREATE_BIGCHAT_TRIGGER in text


def is_reminder(text: str) -> bool:
    return REMINDER_TRIGGER in text


def parse_create_bigchat(text: str) -> CreateBigchat:
    after = text.split(CREATE_BIGCHAT_TRIGGER, maxsplit=1)[1]
    return CreateBigchat(strip_mentions(after.split("\n")[0]))


def parse_reminder(text: str, anna_id: str) -> Reminder:
    """실행자와 중복 멘션은 유지하고 안나만 대상에서 뺀다."""
    if REMINDER_BROADCAST_PHRASE in text:
        return Reminder("broadcast")
    if REMINDER_TEST_PHRASE in text:
        targets = tuple(
            user_id
            for user_id in SLACK_USER_PATTERN.findall(text)
            if user_id != anna_id
        )
        return Reminder("test", targets)
    return Reminder("usage")
