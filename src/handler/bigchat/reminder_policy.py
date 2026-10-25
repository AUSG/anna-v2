import re
from datetime import date
from typing import Iterable, List, Optional, Tuple

from util.bigchat_event import BigchatEvent, parse_sheet_name

# 소속(회사명 등)에 '@' 가 들어가는 경우와 구분하기 위해, 이메일 형태인 셀만 집는다
EMAIL_PAT = re.compile(r"^\S+@\S+\.\S+$")


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


def applicant_email(row: Iterable[str]) -> Optional[str]:
    """열이 밀린 행에서도 이메일 형태인 첫 셀만 고른다."""
    return next(
        (cell.strip().lower() for cell in row if EMAIL_PAT.match(cell.strip())),
        None,
    )
