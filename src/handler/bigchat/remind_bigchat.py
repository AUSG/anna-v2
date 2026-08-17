import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional

from util.bigchat_event import KST, BigchatEvent, parse_sheet_name
from util.utils import strip_multiline

logger = logging.getLogger(__name__)

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 소속(회사명 등)에 '@' 가 들어가는 경우와 구분하기 위해, 이메일 형태인 셀만 집는다
EMAIL_PAT = re.compile(r"^\S+@\S+\.\S+$")


class RemindBigchat:
    """빅챗 전날 저녁, 신청자들에게 내일 잊지 말고 오라는 리마인더 DM 을 보낸다.

    신청 시트의 행에는 슬랙 id 가 없으므로, 행의 이메일을 멤버 시트의
    이메일과 대조해 슬랙 계정을 역추적한다 (탈퇴 취소가 이메일 기준인 것과 동일).
    """

    def __init__(self, slack_client, gs_client, member_manager):
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager

    def run(self, now: Optional[datetime] = None) -> int:
        """내일 시작하는 모든 빅챗의 신청자에게 DM 을 보내고, 보낸 DM 수를 반환한다."""
        now = now or datetime.now(KST)
        tomorrow = (now + timedelta(days=1)).date()

        sent_cnt = 0
        for worksheet_id, title in self.gs_client.list_worksheets():
            event = parse_sheet_name(title)
            if not event or event.start.date() != tomorrow:
                continue
            sent_cnt += self._remind_applicants(worksheet_id, event)
        return sent_cnt

    def _remind_applicants(self, worksheet_id: int, event: BigchatEvent) -> int:
        msg = self._build_reminder(event)
        email_to_slack_id = self.member_manager.email_to_slack_ids()

        sent_cnt = 0
        for email in self._applicant_emails(worksheet_id):
            slack_id = email_to_slack_id.get(email)
            if not slack_id:
                logger.warning(
                    "Applicant not found in members sheet, skipping DM: %s (%s)",
                    email,
                    event.name,
                )
                continue
            try:
                self.slack_client.send_direct_message(user_id=slack_id, msg=msg)
                sent_cnt += 1
            except Exception:
                # 한 명에게 실패해도 (계정 비활성화 등) 나머지에겐 계속 보낸다
                logger.exception("Failed to DM %s (%s)", slack_id, event.name)
        return sent_cnt

    def _applicant_emails(self, worksheet_id: int) -> List[str]:
        """신청 시트 각 행의 이메일 목록.

        수기 수정으로 열이 밀렸을 수 있어 이메일 형태의 첫 셀을 찾고, 중복 신청은 한 번만 센다.
        """
        emails = []
        for row in self.gs_client.get_values(worksheet_id):
            email = next(
                (cell.strip().lower() for cell in row if EMAIL_PAT.match(cell.strip())),
                None,
            )
            if email and email not in emails:
                emails.append(email)
        return emails

    @staticmethod
    def _build_reminder(event: BigchatEvent) -> str:
        d = event.start
        when = (
            f"{d.month}월 {d.day}일 ({WEEKDAYS_KO[d.weekday()]}) "
            f"{d.strftime('%H:%M')}~{event.end.strftime('%H:%M')}"
        )
        return strip_multiline(
            f"""
            :wave: 안녕! 내일 *{event.name}* 빅챗이 열리는 날이야.
            :calendar: {when}
            잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"""
        )
