"""빅챗 이벤트, 입력 명령과 처리 결과. SDK나 실행 환경에 의존하지 않는다."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional

from shared.time import KST

SHEET_NAME_PAT = re.compile(
    r"^(?P<name>.+) (?P<date>\d{2}-\d{2}-\d{2}) (?P<start>\d{2}:\d{2})~(?P<end>\d{2}:\d{2})$"
)


@dataclass
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


class InvalidBigchatName(ValueError):
    pass


class CalendarUnavailable(Exception):
    """캘린더 제공이 꺼져 있거나 이벤트를 찾을 수 없다."""


class CalendarAccessDenied(Exception):
    """다운로드 토큰이 요청한 이벤트/스레드와 일치하지 않는다."""


@dataclass(frozen=True)
class CreateBigchatCommand:
    sheet_name: str

    def __post_init__(self):
        if not parse_sheet_name(self.sheet_name):
            raise InvalidBigchatName(self.sheet_name)


@dataclass(frozen=True)
class BigchatCreated:
    worksheet_id: int
    sheet_name: str
    sheet_url: str


@dataclass
class ReminderResult:
    target_date: date
    bigchat_names: List[str] = field(default_factory=list)
    parsed_sheet_cnt: int = 0
    ignored_sheet_cnt: int = 0
    applicant_cnt: int = 0
    resolved_cnt: int = 0
    sent_cnt: int = 0
