import logging
import threading
import time
from typing import Callable, Dict, Optional, Tuple

from features.members.models import Member
from shared.gateways import SheetsGateway

logger = logging.getLogger(__name__)

# 열 순서: user_id, kor_name, eng_name, email, phone, school_name or company_name
MEMBER_INFO_COLUMNS = "J:O"


class MemberManager:
    """멤버 시트를 읽어 슬랙 계정과 회원 정보를 잇는다.

    시트 생성 직후의 일괄 등록이 N명을 연달아 조회해도 멤버 시트 읽기는 한 번이면
    되도록 결과를 ttl 동안 공유한다. ttl 이 길면 방금 멤버 시트에 추가된 사람이 그만큼
    늦게 조회되므로 60초로 짧게 잡았다. gunicorn 이 스레드 8개로 뜨므로 락으로 보호한다.
    """

    def __init__(
        self,
        sheets: SheetsGateway,
        members_worksheet_id: int,
        *,
        ttl_sec: float = 60,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.sheets = sheets
        self.members_worksheet_id = int(members_worksheet_id)
        self.ttl_sec = ttl_sec
        self.clock = clock
        self._lock = threading.Lock()
        self._cached: Optional[Tuple[float, Dict[str, Member]]] = None

    def find(self, slack_user_id: str) -> Optional[Member]:
        member = self._members().get(slack_user_id)
        logger.debug(member)
        return member

    def email_to_slack_ids(self) -> Dict[str, str]:
        return {
            member.email.strip().lower(): user_id
            for user_id, member in self._members().items()
            if member.email.strip()
        }

    def _members(self) -> Dict[str, Member]:
        with self._lock:
            now = self.clock()
            if self._cached is None or now - self._cached[0] >= self.ttl_sec:
                rows = self.sheets.get_values(
                    self.members_worksheet_id, MEMBER_INFO_COLUMNS
                )
                self._cached = (now, build_members(rows))
            return self._cached[1]


def build_members(rows) -> Dict[str, Member]:
    members = {}
    for row in rows[1:]:  # [0] == header row
        if not row:
            continue
        user_id = row[0]
        if len(row) < 6:
            continue  # 일부 값이 누락된 행
        kor_name, eng_name, email, phone, school_name_or_company_name = row[1:6]
        members[user_id] = Member(
            kor_name=kor_name,
            eng_name=eng_name,
            email=email,
            phone=phone,
            school_name_or_company_name=school_name_or_company_name,
        )
    return members
