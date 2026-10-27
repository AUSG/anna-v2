"""커뮤니티 회원 값과 조회 오류."""

from typing import List

from pydantic import BaseModel


class Member(BaseModel):
    kor_name: str
    eng_name: str
    email: str
    phone: str
    school_name_or_company_name: str

    def transform_for_spreadsheet(self) -> List[str]:
        return [self.kor_name, self.school_name_or_company_name, self.email, self.phone]


class MemberNotFound(Exception):
    pass


class MemberLackInfo(Exception):
    pass
