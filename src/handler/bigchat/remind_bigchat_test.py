import logging
import re

from handler.bigchat.mention_handler import MentionHandler
from handler.bigchat.remind_bigchat import RemindBigchat, ReminderResult
from util.utils import strip_multiline

logger = logging.getLogger(__name__)

TRIGGER = "빅챗 리마인더 테스트"
SLACK_USER_PAT = re.compile(r"<@([A-Z0-9]+)>")


class RemindBigchatTest(MentionHandler):
    """리마인더 발송을 18시까지 기다리지 않고 지금 돌려보는 수동 트리거.

    `@ANNA 빅챗 리마인더 테스트 @누구` 로 실행하면, 실제 스케줄과 똑같이
    "지금 기준 내일" 시작하는 빅챗을 찾아 발송 경로를 그대로 태우되,
    DM 은 멘션한 사람들에게만 간다. 대상 없이 실행하면 아무것도 보내지 않는다
    (실수로 신청자 전원에게 나가는 일이 없도록 대상 지정을 필수로 뒀다).
    """

    def __init__(self, event, slack_client, gs_client, member_manager, anna_id):
        self.text = event["text"]
        self.ts = event["ts"]
        self.channel = event["channel"]
        self.user = event["user"]
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.anna_id = anna_id

    def can_handle(self):
        return TRIGGER in self.text

    def handle_mention(self):
        if not self.can_handle():
            return False

        targets = self._target_user_ids()
        if not targets:
            self._reply(
                strip_multiline(
                    f"""
                    받을 사람을 같이 멘션해줘! 실수로 신청자 전원에게 나가지 않게 대상 지정을 필수로 해뒀어.
                    예) `@ANNA {TRIGGER} <@{self.user}>`"""
                )
            )
            return False

        logger.info(
            "Manual reminder test triggered by %s, targets=%s", self.user, targets
        )
        result = RemindBigchat(
            self.slack_client, self.gs_client, self.member_manager
        ).run(only_user_ids=targets)
        self._reply(self._build_report(result, targets))
        return True

    def _target_user_ids(self):
        """멘션된 슬랙 계정들. 자기 자신에게 보내보는 게 정상 사용이라 실행자도 제외하지 않는다."""
        return [
            user_id
            for user_id in SLACK_USER_PAT.findall(self.text)
            if user_id != self.anna_id
        ]

    @staticmethod
    def _build_report(result: ReminderResult, targets) -> str:
        target_txt = ", ".join(f"<@{user_id}>" for user_id in targets)
        if not result.bigchat_names:
            return strip_multiline(
                f"""
                {result.target_date} 에 시작하는 빅챗을 못 찾았어. 그래서 보낼 것도 없었어.
                - 빅챗 이름 형식(`<이름> yy-MM-DD HH:mm~HH:mm`)으로 읽힌 시트: {result.parsed_sheet_cnt}개
                - 형식이 안 맞아서 무시한 시트: {result.ignored_sheet_cnt}개
                시트 이름이 이 형식인지 확인해줘! 자세한 목록은 로그에 남겼어."""
            )
        found = ", ".join(result.bigchat_names)
        return strip_multiline(
            f"""
            {result.target_date} 빅챗 `{found}` 찾았어!
            테스트 DM 을 {target_txt} 에게 보냈어 ({result.sent_cnt}건).
            실제 발송이었다면 이렇게 나갔을 거야:
            - 신청 시트에서 찾은 신청자: {result.applicant_cnt}명
            - 그 중 멤버 시트에서 슬랙 계정을 찾은 사람: {result.resolved_cnt}명
            (둘이 다르면 신청 시트 이메일과 멤버 시트 이메일이 안 맞는 거야. 로그에 누군지 남겼어!)"""
        )

    def _reply(self, msg: str):
        self.slack_client.send_message_only_visible_to_user(
            msg=msg, channel=self.channel, ts=self.ts, user_id=self.user
        )
