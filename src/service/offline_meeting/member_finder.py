import os
from typing import Dict

from exception import RuntimeException
from implementation import GoogleSpreadsheetClient
from .member import Member

FORM_SPREADSHEET_ID = os.environ.get('FORM_SPREADSHEET_ID')
MEMBERS_INFO_WORKSHEET_ID = int(os.environ.get('MEMBERS_INFO_WORKSHEET_ID'))


def find_member(gs_client: GoogleSpreadsheetClient, slack_unique_id: str) -> Member:
    found_member = fetch_members(gs_client).get(slack_unique_id)
    if found_member is None:
        raise RuntimeException(f"멤버 정보를 찾지 못했어요. (slack_unique_id: {slack_unique_id})")
    elif not validate_member_info(found_member):
        raise RuntimeException(f"멤버 정보가 완벽하지 않아요. (slack_unique_id: {slack_unique_id}, member_info: {found_member})")
    return found_member


def fetch_members(gs_client: GoogleSpreadsheetClient) -> Dict[str, Member]:
    member_info_cols = 'J:O'  # 열 순서: user_id, kor_name, eng_name, email, phone, school_name or company_name # TODO [seonghyeok] 환경변수로 빼기
    raw_members = gs_client.get_values(MEMBERS_INFO_WORKSHEET_ID, member_info_cols)

    members = {}
    for m in raw_members[1:]:  # [0] == header row
        user_id = m[0]
        try:
            members[user_id] = Member(kor_name=m[1],
                                      eng_name=m[2],
                                      email=m[3],
                                      phone=m[4],
                                      school_name_or_company_name=m[5])
        except IndexError:
            pass  # 유저 정보가 부족할 때 발생할 수 있다고 예상됨 (확인은 안해봄)

    return members


def validate_member_info(m: Member):
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
    return True
