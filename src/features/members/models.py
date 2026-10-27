"""커뮤니티 회원 값."""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Member:
    kor_name: str
    eng_name: str
    email: str
    phone: str
    school_name_or_company_name: str

    def is_complete(self) -> bool:
        """빅챗 신청 시트에 적을 수 있을 만큼 정보가 채워졌는지."""
        return (
            len(self.kor_name) > 0
            and len(self.eng_name) > 0
            and len(self.email) > 0
            and len(self.phone) == 13
            and len(self.school_name_or_company_name) > 0
        )

    def transform_for_spreadsheet(self) -> List[str]:
        return [self.kor_name, self.school_name_or_company_name, self.email, self.phone]
