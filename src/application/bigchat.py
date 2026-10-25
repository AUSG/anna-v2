from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, List, Tuple

from util.bigchat_event import BigchatEvent, parse_sheet_name


class InvalidBigchatName(ValueError):
    pass


@dataclass(frozen=True)
class CreateBigchatCommand:
    sheet_name: str

    def __post_init__(self):
        # 시트 이름은 안내문에도 쓰이므로 검증할 때 원문을 바꾸지 않는다.
        if not parse_sheet_name(self.sheet_name):
            raise InvalidBigchatName(self.sheet_name)


@dataclass(frozen=True)
class BigchatCreated:
    worksheet_id: int
    sheet_name: str
    sheet_url: str


@dataclass
class ReminderResult:
    """한 번의 발송 시도 요약. 수동 트리거가 이걸로 결과 메시지를 만든다."""

    target_date: date
    bigchat_names: List[str] = field(default_factory=list)
    parsed_sheet_cnt: int = 0
    ignored_sheet_cnt: int = 0
    applicant_cnt: int = 0  # 신청 시트에서 찾은 이메일 수
    resolved_cnt: int = 0  # 그 중 멤버 시트에서 슬랙 계정을 찾은 수
    sent_cnt: int = 0


def select_bigchats(
    worksheets: Iterable[Tuple[int, str]], target_date: date
) -> Tuple[List[Tuple[int, BigchatEvent]], List[str], List[str]]:
    matched, parsed, ignored = [], [], []
    for worksheet_id, title in worksheets:
        event = parse_sheet_name(title)
        if not event:
            ignored.append(title)
            continue
        parsed.append(f"{title!r} -> starts {event.start.date()}")
        if event.start.date() == target_date:
            matched.append((worksheet_id, event))
    return matched, parsed, ignored
