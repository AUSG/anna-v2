import os
from typing import Dict

from exception import RuntimeException
from implementation import GoogleSpreadsheetClient
from .member import Member


# TODO [seonghyeok] 부모 클래스 형태로 캐시 레이어 구현
class MemberFinder:
    def __init__(self, gs_client: GoogleSpreadsheetClient):
        self.gs_client = gs_client
        self.spreadsheet_id = os.environ.get('FORM_SPREADSHEET_ID')
        self.members_worksheet_id = int(os.environ.get('MEMBERS_INFO_WORKSHEET_ID'))

    def find(self, slack_unique_id: str) -> Member:
        members = self._fetch_members()

        member = members.get(slack_unique_id)

        if not member:
            raise RuntimeException(f"멤버 정보를 찾지 못했어요. (slack_unique_id: {slack_unique_id})")
        elif not self._validate_member_info(member):
            raise RuntimeException(f"멤버 정보가 완벽하지 않아요. (slack_unique_id: {slack_unique_id}, member_info: {member})")
        else:
            return member

    def _fetch_members(self) -> Dict[str, Member]:
        member_info_cols = 'J:O'  # 열 순서: user_id, kor_name, eng_name, email, phone, school_name or company_name # TODO [seonghyeok] 환경변수로 빼기
        raw_members = self.gs_client.get_values(self.spreadsheet_id, self.members_worksheet_id, member_info_cols)

        members = self._build_members_info(raw_members)
        return members

    def _build_members_info(self, raw_members):
        members = {}
        for m in raw_members[1:]:  # [0] == header row
            user_id = m[0]
            try:
                kor_name, eng_name, email, phone, school_name_or_company_name = m[1:6]
                members[user_id] = Member(kor_name, eng_name, email, phone, school_name_or_company_name)
            except (IndexError, ValueError):
                pass  # 일부 값이 누락될 경우 이쪽으로 올 수 있다
        return members

    def _validate_member_info(self, m: Member):
        if (m.kor_name is None or
                m.eng_name is None or
                m.email is None or
                m.phone is None or
                m.school_name_or_company_name is None or
                len(m.kor_name) == 0 or
                len(m.eng_name) == 0 or
                len(m.email) == 0 or
                len(m.phone) != 13 or
                len(m.school_name_or_company_name) == 0):
            return False
        else:
            return True
