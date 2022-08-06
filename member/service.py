import logging

import env_bucket
from google_spreadsheet_client import GsClient
from member.member import Member

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("member.service")

MEMBERS_INFO_WORKSHEET_ID = env_bucket.get('MEMBERS_INFO_WORKSHEET_ID')


class MemberService:
    """
    [CAVEAT] 처음 서버가 뜬 이후 멤버 정보를 최초 한 번만 캐싱하고 expire 하지 않음. 업데이트하려면 서버 다시 띄워야 됨.
    [CAVEAT] __init__ 을 override 해서 싱글턴 패턴을 구현하고 싶은데 방법을 잘 모르겠음. 개선 전까진 사용하는 client 쪽에서 싱글턴 적용
    """

    def __init__(self, gs_client: GsClient):
        self.gs_client = gs_client
        self.members = {}  # AUSG 멤버들 전체에 대한 캐시 데이터. key: 슬랙 고유 id (ex. U01BN035Y6L)
        self._cache_members()

    def submit_form(self, slack_unique_id: str, worksheet_id: int):
        member = self.members[slack_unique_id]

        if not self._all_field_filled(member):
            logging.error(f"모든 필드가 완벽하게 존재하지 않는 불완전한 멤버 정보입니다: {member}")
            raise Exception()  # TODO [seonghyeok] 메시지를 받는 형태로 예외를 만들어 슬랙까지 전달

        self.gs_client.append_row(worksheet_id,
                                  [member.email,
                                   member.kor_name,
                                   member.eng_name,
                                   member.phone,
                                   member.school_name_or_company_name])

    def _cache_members(self):
        if len(self.members) > 0:
            return self.members

        # 열 순서: userid, kor_name, eng_name, email, phone, school_name or company_name
        members = self.gs_client.get_values(MEMBERS_INFO_WORKSHEET_ID, 'J:O')

        for m in members:
            self.members[m[0]] = Member(kor_name=m[1],
                                        eng_name=m[2],
                                        email=m[3],
                                        phone=m[4],
                                        school_name_or_company_name=m[5])

    def _all_field_filled(self, member: Member) -> bool:
        try:
            if (len(member.kor_name) == 0 or
                    len(member.eng_name) == 0 or
                    len(member.email) == 0 or
                    len(member.phone) != 13 or
                    len(member.school_name_or_company_name) == 0):
                return False
            else:
                return True
        except Exception as e:
            logging.error(e)
            return False
