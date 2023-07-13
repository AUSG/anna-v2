import logging
from typing import Dict, List

from cachetools.func import ttl_cache
from pydantic import BaseModel

from config.env_config import envs
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient


class Member(BaseModel):
    kor_name: str
    eng_name: str
    email: str
    phone: str
    school_name_or_company_name: str

    def transform_for_spreadsheet(self) -> List[str]:
        return [
            self.eng_name.split(" ", 1)[0],  # first name
            self.eng_name.split(" ", 1)[1],  # last name
            self.eng_name,  # full name
            self.email,  # email
            self.school_name_or_company_name,  # school or company
            self.phone,  # phone
        ]


class MemberNotFound(Exception):
    pass


class MemberLackInfo(Exception):
    pass


class MemberManager:
    def __init__(self, gs_client: GoogleSpreadsheetClient):
        self.gs_client = gs_client
        self.members_worksheet_id = int(envs.MEMBERS_INFO_WORKSHEET_ID)
        self.logger = logging.getLogger(__name__)

    @ttl_cache(
        maxsize=30, ttl=600
    )  # not thread-safe, 'maxsize' means 'cache call limit'
    def find(self, slack_unique_id: str) -> Member:
        members = self._fetch_members()

        member = members.get(slack_unique_id)

        if not member:
            raise MemberNotFound()
        if not self._validate_member_info(member):
            raise MemberLackInfo()
        self.logger.debug(member)
        return member

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

    @staticmethod
    def _is_member_in_worksheet(ws_rows, member):
        for num, row in enumerate(ws_rows, start=1):
            if member.email in row:
                return num
        return None

    def add_member_to_bigchat_worksheet(
        self,
        member,
        worksheet_id,
    ):
        self.gs_client.append_row(worksheet_id, member.transform_for_spreadsheet())
