"""빅챗 이벤트, 입력 명령과 처리 결과. SDK나 실행 환경에 의존하지 않는다."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum, auto
from typing import List, Literal, Optional, Tuple

from features.members.models import Member
from shared.time import KST

SHEET_NAME_PAT = re.compile(
    r"^(?P<name>.+) (?P<date>\d{2}-\d{2}-\d{2}) (?P<start>\d{2}:\d{2})~(?P<end>\d{2}:\d{2})$"
)


@dataclass(frozen=True)
class BigchatEvent:
    name: str
    start: datetime
    end: datetime


def parse_sheet_name(sheet_name: str) -> Optional[BigchatEvent]:
    """이벤트 이름 형식, 실제 날짜/시각, 종료가 시작보다 늦은지 검증한다."""
    match = SHEET_NAME_PAT.match(sheet_name.strip())
    if not match:
        return None
    try:
        start = datetime.strptime(
            f"{match['date']} {match['start']}", "%y-%m-%d %H:%M"
        ).replace(tzinfo=KST)
        end = datetime.strptime(
            f"{match['date']} {match['end']}", "%y-%m-%d %H:%M"
        ).replace(tzinfo=KST)
    except ValueError:
        return None
    if end <= start:
        return None
    return BigchatEvent(name=match["name"].strip(), start=start, end=end)


@dataclass(frozen=True)
class CreateBigchatCommand:
    """검증을 통과한 시트 이름. parse() 로만 만든다."""

    sheet_name: str
    event: BigchatEvent

    @classmethod
    def parse(cls, sheet_name: str) -> Optional["CreateBigchatCommand"]:
        # 시트 이름은 안내문에도 쓰이므로 원문을 바꾸지 않는다.
        event = parse_sheet_name(sheet_name)
        return cls(sheet_name, event) if event else None


@dataclass(frozen=True)
class BigchatCreated:
    worksheet_id: int
    sheet_name: str
    sheet_url: str


class RegistrationStatus(Enum):
    REGISTERED = auto()
    ALREADY_REGISTERED = auto()
    MEMBER_NOT_FOUND = auto()
    MEMBER_LACKS_INFO = auto()
    WORKSHEET_MISSING = auto()


@dataclass(frozen=True)
class Registration:
    status: RegistrationStatus
    member: Optional[Member] = None


class CancellationStatus(Enum):
    CANCELLED = auto()
    MEMBER_NOT_FOUND = auto()
    MEMBER_LACKS_INFO = auto()
    WORKSHEET_MISSING = auto()


@dataclass(frozen=True)
class CalendarLinks:
    gcal_url: str
    ics_url: Optional[str] = None


@dataclass(frozen=True)
class CalendarContext:
    event: BigchatEvent
    description: str


@dataclass(frozen=True)
class CalendarFailure:
    reason: Literal["denied", "unavailable"]


@dataclass
class ReminderResult:
    target_date: date
    bigchat_names: List[str] = field(default_factory=list)
    parsed_sheet_cnt: int = 0
    ignored_sheet_cnt: int = 0
    applicant_cnt: int = 0  # 신청 시트에서 찾은 이메일 수
    resolved_cnt: int = 0  # 그 중 멤버 시트에서 슬랙 계정을 찾은 수
    sent_cnt: int = 0


Recipients = List[Tuple[str, Optional[str]]]  # (slack_id, email)
