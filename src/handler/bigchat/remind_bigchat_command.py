import logging
import re

from application.bigchat import ReminderResult
from handler.bigchat.mention_handler import MentionHandler
from handler.bigchat.remind_bigchat import RemindBigchat
from handler.bigchat.reminder_messages import (
    BROADCAST_PHRASE,
    TEST_PHRASE,
    TRIGGER as TRIGGER,
    USAGE,
    build_report,
    missing_targets_message,
)
from handler.mention_router import matches_mention

logger = logging.getLogger(__name__)

SLACK_USER_PAT = re.compile(r"<@([A-Z0-9]+)>")


class RemindBigchatCommand(MentionHandler):
    """예약 시각을 기다리지 않고 내일 빅챗의 리마인더를 실행한다.

    테스트는 멘션 대상에게, 전원 발송은 신청자에게 보낸다.
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
        return matches_mention("reminder", self.text)

    def handle_mention(self):
        if not self.can_handle():
            return False
        if BROADCAST_PHRASE in self.text:
            return self._broadcast()
        if TEST_PHRASE in self.text:
            return self._test()
        self._reply(USAGE)
        return False

    def _broadcast(self):
        logger.warning(
            "Manual reminder BROADCAST triggered by %s — sending to every applicant",
            self.user,
        )
        result = self._run()
        self._reply(self._build_report(result, targets=None))
        return True

    def _test(self):
        targets = self._target_user_ids()
        if not targets:
            self._reply(missing_targets_message(self.user))
            return False

        logger.info(
            "Manual reminder test triggered by %s, targets=%s", self.user, targets
        )
        result = self._run(only_user_ids=targets)
        self._reply(self._build_report(result, targets))
        return True

    def _run(self, only_user_ids=None) -> ReminderResult:
        return RemindBigchat(
            self.slack_client, self.gs_client, self.member_manager
        ).run(only_user_ids=only_user_ids)

    def _target_user_ids(self):
        """멘션 대상을 고른다. 실행자와 중복은 유지하고 안나만 제외한다."""
        return [
            user_id
            for user_id in SLACK_USER_PAT.findall(self.text)
            if user_id != self.anna_id
        ]

    @staticmethod
    def _build_report(result: ReminderResult, targets) -> str:
        return build_report(result, targets)

    def _reply(self, msg: str):
        self.slack_client.send_message_only_visible_to_user(
            msg=msg, channel=self.channel, ts=self.ts, user_id=self.user
        )
