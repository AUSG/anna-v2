from typing import Dict, Optional, Protocol

from features.members.models import Member


class MemberDirectory(Protocol):
    def find(self, slack_user_id: str) -> Optional[Member]:
        """멤버 시트에 없으면 None. 정보가 비었는지는 Member.is_complete() 로 본다."""
        ...

    def email_to_slack_ids(self) -> Dict[str, str]:
        """이메일(소문자) → 슬랙 user_id."""
        ...
