"""외부 조회 없이 리마인더 대상 시트와 신청 이메일을 고른다."""

import re
from datetime import date
from typing import Iterable, List, Optional, Tuple

from features.bigchat.models import BigchatEvent, parse_sheet_name

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
