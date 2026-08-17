import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import List, Optional

from util.bigchat_event import KST, BigchatEvent, parse_sheet_name
from util.utils import strip_multiline

logger = logging.getLogger(__name__)

WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 소속(회사명 등)에 '@' 가 들어가는 경우와 구분하기 위해, 이메일 형태인 셀만 집는다
EMAIL_PAT = re.compile(r"^\S+@\S+\.\S+$")


@dataclass
class ReminderResult:
    """한 번의 발송 시도 요약. 수동 트리거가 이걸로 결과 메시지를 만든다."""

    target_date: date
    bigchat_names: List[str] = field(default_factory=list)
    parsed_sheet_cnt: int = 0
    ignored_sheet_cnt: int = 0
    applicant_cnt: int = 0  # 신청 시트에서 찾은 이메일 수
    resolved_cnt: int = 0  # 그 중 멤버 시트에서 슬랙 계정을 찾은 수
    sent_cnt: int = 0


class RemindBigchat:
    """빅챗 전날 저녁, 신청자들에게 내일 잊지 말고 오라는 리마인더 DM 을 보낸다.

    신청 시트의 행에는 슬랙 id 가 없으므로, 행의 이메일을 멤버 시트의
    이메일과 대조해 슬랙 계정을 역추적한다 (탈퇴 취소가 이메일 기준인 것과 동일).
    """

    def __init__(self, slack_client, gs_client, member_manager):
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager

    def run(
        self,
        now: Optional[datetime] = None,
        only_user_ids: Optional[List[str]] = None,
    ) -> ReminderResult:
        """내일 시작하는 모든 빅챗의 신청자에게 DM 을 보낸다.

        :param only_user_ids: 주면 신청자 대신 이 슬랙 계정들에게만 보낸다 (수동 트리거 테스트용).
          신청자 조회/매칭은 그대로 수행하고 로그도 남기므로, 실제 발송 경로를 그대로 점검할 수 있다.
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
        matched, parsed, ignored = [], [], []
        for worksheet_id, title in worksheets:
            event = parse_sheet_name(title)
            if not event:
                ignored.append(title)
                continue
            parsed.append(f"{title!r} -> starts {event.start.date()}")
            if event.start.date() == tomorrow:
                matched.append((worksheet_id, event))

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

        # 신청자 -> 슬랙 계정 해석은 테스트 모드에서도 그대로 수행한다 (로그로 매칭 상태를 보려고)
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
        """신청 시트 각 행의 이메일 목록.

        수기 수정으로 열이 밀렸을 수 있어 이메일 형태의 첫 셀을 찾고, 중복 신청은 한 번만 센다.
        """
        rows = self.gs_client.get_values(worksheet_id)
        emails, skipped_rows = [], 0
        for row in rows:
            email = next(
                (cell.strip().lower() for cell in row if EMAIL_PAT.match(cell.strip())),
                None,
            )
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
