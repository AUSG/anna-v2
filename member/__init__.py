import logging
from datetime import datetime
from pprint import pformat

import gspread
from gspread_formatting import *
from slack_sdk import WebClient

from member.member import Member

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

FORM_SPREADSHEET = '1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k'  # "AUSG_오프라인_모임_참가신청서" # TODO [seonghyeok] env 로 빼기
MEMBERS_INFO_WORKSHEET_ID = 307140510  # TODO [seonghyeok] env 로 빼기


class MemberService:
    """
    [CAVEAT] 처음 서버가 뜬 이후 멤버 정보를 최초 한 번만 캐싱하고 expire 하지 않음. 업데이트하려면 서버 다시 띄워야 됨.
    [CAVEAT] __init__ 을 override 해서 싱글턴 패턴을 구현하고 싶은데 방법을 잘 모르겠음. 개선 전까진 사용하는 client 쪽에서 싱글턴 적용
    """

    def __init__(self):
        self.gs_client = gspread.service_account(filename='./gcp_serviceaccount_secret.json')
        self.members_info = {}  # AUSG 멤버들 전체에 대한 캐시 데이터. key: 슬랙 고유 id (ex. U01BN035Y6L)
        self._cache_members_info()

    def create_worksheet(self):
        spreadsheet = self.gs_client.open_by_key(FORM_SPREADSHEET)

        now = datetime.now().strftime('%Y/%m/%d-%H%M%S')
        worksheet = spreadsheet.add_worksheet(f"[제목고쳐줘] {now}", rows=100, cols=30)
        worksheet.append_row(["타임스탬프", "이메일 주소", "이름", "영문 이름", "휴대폰 번호", "학교명 혹은 회사명"])
        set_column_width(worksheet, 'A:F', 220)

        return worksheet.id

    def submit_form(self, slack_unique_id: str, worksheet_id: int):
        worksheet = self._get_worksheet(worksheet_id)

        member = self.members_info[slack_unique_id]
        now = str(datetime.now())

        worksheet.append_row([now, member.email, member.kor_name, member.eng_name, member.phone, member.school_name_or_company_name])

    def _all_field_filled(self, member_info):
        try:
            if (len(member_info['kor_name']) == 0 or
                    len(member_info['eng_name']) == 0 or
                    len(member_info['email']) == 0 or
                    len(member_info['phone']) != 13 or
                    len(member_info['school_name or company_name']) == 0):
                return False
            else:
                return True
        except Exception as e:
            logging.error(e)
            return False

    def _cache_members_info(self, ):
        if len(self.members_info) > 0:
            return self.members_info

        members_worksheet = self._get_worksheet(MEMBERS_INFO_WORKSHEET_ID)

        # 순서: userid, kor_name, eng_name, email, phone, school_name or company_name
        members = members_worksheet.get_values('J:O')

        for m in members:
            self.members_info[m[0]] = Member(kor_name=m[1],
                                             eng_name=m[2],
                                             email=m[3],
                                             phone=m[4],
                                             school_name_or_company_name=m[5])

    def _get_worksheet(self, worksheet_id: int):
        spreadsheet = self.gs_client.open_by_key(FORM_SPREADSHEET)  # 'AUSG_오프라인_모임_참가신청서'
        members_worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
        return members_worksheet

    if __name__ == '__main__':
        # get_member_info('UQJ8HQJG5')  # TEST, 문성혁 id
        # _id = create_worksheet()
        # pprint(_id)
        pass
