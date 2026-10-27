import logging
from typing import Dict

from cachetools.func import ttl_cache
from config.env_config import envs
from features.members.models import Member, MemberLackInfo, MemberNotFound
from integrations.google_sheets import GoogleSpreadsheetClient


class MemberManager:
    def __init__(self, gs_client: GoogleSpreadsheetClient):
        self.gs_client = gs_client
        self.members_worksheet_id = int(envs.MEMBERS_INFO_WORKSHEET_ID)
        self.logger = logging.getLogger(__name__)

    @ttl_cache(maxsize=30, ttl=600)
    def find(self, slack_unique_id: str) -> Member:
        members = self._fetch_members()

        member = members.get(slack_unique_id)

        if not member:
            raise MemberNotFound()
        if not self._validate_member_info(member):
            raise MemberLackInfo()
        self.logger.debug(member)
        return member

    def email_to_slack_ids(self) -> Dict[str, str]:
        """이메일(소문자) → 슬랙 user_id 매핑. 빅챗 신청 시트의 행(이메일)을 슬랙 계정으로 역추적할 때 쓴다."""
        members = self._fetch_members()
        return {
            member.email.strip().lower(): user_id
            for user_id, member in members.items()
            if member.email.strip()
        }

    @ttl_cache(maxsize=1, ttl=60)
    # 연속된 회원 조회에서 멤버 시트 읽기 결과를 60초간 공유한다.
    def _fetch_members(self) -> Dict[str, Member]:
        member_info_cols = "J:O"  # 열 순서: user_id, kor_name, eng_name, email, phone, school_name or company_name
        raw_members = self.gs_client.get_values(
            self.members_worksheet_id, member_info_cols
        )

        members = self._build_members_info(raw_members)
        return members

    @staticmethod
    def _build_members_info(raw_members):
        members = {}
        for m in raw_members[1:]:  # [0] == header row
            user_id = m[0]
            try:
                kor_name, eng_name, email, phone, school_name_or_company_name = m[1:6]
                members[user_id] = Member(
                    kor_name=kor_name,
                    eng_name=eng_name,
                    email=email,
                    phone=phone,
                    school_name_or_company_name=school_name_or_company_name,
                )
            except (IndexError, ValueError):
                pass  # 일부 값이 누락될 경우 이쪽으로 올 수 있다
        return members

    @staticmethod
    def _validate_member_info(m: Member):
        return (
            m.kor_name is not None
            and m.eng_name is not None
            and m.email is not None
            and m.phone is not None
            and m.school_name_or_company_name is not None
            and len(m.kor_name) > 0
            and len(m.eng_name) > 0
            and len(m.email) > 0
            and len(m.phone) == 13
            and len(m.school_name_or_company_name) > 0
        )
