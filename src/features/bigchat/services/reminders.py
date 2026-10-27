import logging
from datetime import datetime, timedelta
from typing import List, Optional

from features.bigchat.models import ReminderResult as ReminderResult, select_bigchats
from features.bigchat.presentation.reminders import (
    WEEKDAYS_KO as WEEKDAYS_KO,
    build_reminder,
)
from features.bigchat.services.reminder_policy import (
    EMAIL_PAT as EMAIL_PAT,
    applicant_email,
)
from features.bigchat.calendar import KST, BigchatEvent

logger = logging.getLogger(__name__)


class RemindBigchat:
    """신청 이메일을 슬랙 계정과 대조해 내일 빅챗의 리마인더를 보낸다."""

    def __init__(self, slack_client, gs_client, member_manager):
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager

    def run(
        self,
        now: Optional[datetime] = None,
        only_user_ids: Optional[List[str]] = None,
    ) -> ReminderResult:
        """내일 시작하는 빅챗을 찾아 발송하고 결과를 모은다.

        only_user_ids를 지정해도 신청자 조회와 계정 매칭은 수행한다.
        """
        now = now or datetime.now(KST)
        tomorrow = (now + timedelta(days=1)).date()
        logger.info(
            "Reminder run started: now=%s (KST), looking for bigchats starting on %s%s",
            now.isoformat(timespec="seconds"),
            tomorrow,
            f", TEST MODE -> only {only_user_ids}" if only_user_ids else "",
        )

        worksheets = self.gs_client.list_worksheets()
        matched, parsed, ignored = select_bigchats(worksheets, tomorrow)

        # 시트 이름이 곧 이벤트 정보라, 왜 매칭이 안 됐는지는 이 두 줄이면 판단할 수 있다
        logger.info(
            "Scanned %d worksheet(s); %d parsed as bigchat sheets: %s",
            len(worksheets),
            len(parsed),
            parsed or "-",
        )
        logger.info(
            "%d worksheet(s) ignored (name is not '<이름> yy-MM-DD HH:mm~HH:mm'): %s",
            len(ignored),
            ignored or "-",
        )

        result = ReminderResult(
            target_date=tomorrow,
            bigchat_names=[event.name for _, event in matched],
            parsed_sheet_cnt=len(parsed),
            ignored_sheet_cnt=len(ignored),
        )
        if not matched:
            logger.info("No bigchat starts on %s — nothing to remind", tomorrow)
            return result

        logger.info(
            "%d bigchat(s) start on %s: %s",
            len(matched),
            tomorrow,
            result.bigchat_names,
        )
        for worksheet_id, event in matched:
            self._remind_applicants(worksheet_id, event, only_user_ids, result)
        logger.info(
            "Reminder run finished: sent %d DM(s) across %d bigchat(s) "
            "(%d applicant(s), %d resolved to slack accounts)",
            result.sent_cnt,
            len(matched),
            result.applicant_cnt,
            result.resolved_cnt,
        )
        return result

    def _remind_applicants(
        self,
        worksheet_id: int,
        event: BigchatEvent,
        only_user_ids: Optional[List[str]],
        result: ReminderResult,
    ):
        msg = self._build_reminder(event)
        email_to_slack_id = self.member_manager.email_to_slack_ids()
        emails = self._applicant_emails(worksheet_id)
        logger.info(
            "Bigchat %r (worksheet %s): %d applicant(s) in sheet, %d member(s) with email in members sheet",
            event.name,
            worksheet_id,
            len(emails),
            len(email_to_slack_id),
        )
        logger.debug("Reminder message for %r:\n%s", event.name, msg)

        # 테스트 모드에서도 신청자와 계정의 매칭 상태를 확인한다.
        recipients = []
        for email in emails:
            slack_id = email_to_slack_id.get(email)
            if not slack_id:
                logger.warning(
                    "Applicant not found in members sheet, skipping DM: %s (%s)",
                    email,
                    event.name,
                )
                continue
            recipients.append((slack_id, email))
        result.applicant_cnt += len(emails)
        result.resolved_cnt += len(recipients)

        if only_user_ids is not None:
            logger.info(
                "TEST MODE: sending to %s instead of the %d resolved applicant(s)",
                only_user_ids,
                len(recipients),
            )
            recipients = [(user_id, None) for user_id in only_user_ids]

        sent_cnt = 0
        for slack_id, email in recipients:
            try:
                self.slack_client.send_direct_message(user_id=slack_id, msg=msg)
                sent_cnt += 1
                logger.info(
                    "Sent reminder DM to %s <%s> (%s)",
                    slack_id,
                    email or "?",
                    event.name,
                )
            except Exception:
                # 한 명에게 실패해도 (계정 비활성화 등) 나머지에겐 계속 보낸다
                logger.exception(
                    "Failed to DM %s <%s> (%s)", slack_id, email or "?", event.name
                )
        logger.info(
            "Bigchat %r: sent %d of %d intended recipient(s)",
            event.name,
            sent_cnt,
            len(recipients),
        )
        result.sent_cnt += sent_cnt

    def _applicant_emails(self, worksheet_id: int) -> List[str]:
        """각 행의 첫 이메일을 골라 원래 순서대로 중복을 제거한다."""
        rows = self.gs_client.get_values(worksheet_id)
        emails, skipped_rows = [], 0
        for row in rows:
            email = applicant_email(row)
            if not email:
                skipped_rows += 1  # 빈 헤더 행이 보통 하나 있고, 그 외는 수기 편집 흔적일 수 있다
                logger.debug("Worksheet %s: no email in row %r", worksheet_id, row)
                continue
            if email in emails:
                logger.debug(
                    "Worksheet %s: duplicated applicant %s", worksheet_id, email
                )
                continue
            emails.append(email)
        logger.info(
            "Worksheet %s: %d row(s) -> %d unique applicant email(s), %d row(s) without an email",
            worksheet_id,
            len(rows),
            len(emails),
            skipped_rows,
        )
        return emails

    @staticmethod
    def _build_reminder(event: BigchatEvent) -> str:
        return build_reminder(event)
