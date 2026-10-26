import re
from typing import Iterable, Optional

from application.bigchat import select_bigchats as select_bigchats

# 소속(회사명 등)에 '@' 가 들어가는 경우와 구분하기 위해, 이메일 형태인 셀만 집는다
EMAIL_PAT = re.compile(r"^\S+@\S+\.\S+$")


def applicant_email(row: Iterable[str]) -> Optional[str]:
    """열이 밀린 행에서도 이메일 형태인 첫 셀만 고른다."""
    return next(
        (cell.strip().lower() for cell in row if EMAIL_PAT.match(cell.strip())),
        None,
    )
