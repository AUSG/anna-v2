import logging
import re

from handler.bigchat.mention_handler import MentionHandler
from handler.bigchat.remind_bigchat import RemindBigchat, ReminderResult
from util.utils import strip_multiline

logger = logging.getLogger(__name__)

TRIGGER = "빅챗 리마인더"
TEST_PHRASE = "테스트"
# 전원 발송은 되돌릴 수 없어서, 이 문구를 통째로 쳐야만 실행된다
BROADCAST_PHRASE = "지금 전원 발송"

SLACK_USER_PAT = re.compile(r"<@([A-Z0-9]+)>")

USAGE = strip_multiline(
    f"""
    빅챗 리마인더를 저녁 6시까지 기다리지 않고 지금 돌릴 수 있어.
    - `{TRIGGER} {TEST_PHRASE} @받을사람`: 멘션한 사람에게만 보내볼게 (발송이 되는지 확인용)
    - `{TRIGGER} {BROADCAST_PHRASE}`: 내일 빅챗 신청자 *전원*에게 진짜로 보낼게"""
)


class RemindBigchatCommand(MentionHandler):
    """리마인더를 18시 스케줄과 무관하게 지금 실행하는 멘션 명령.

    두 모드 모두 "지금 기준 내일" 시작하는 빅챗을 실제 스케줄과 똑같이 찾는다.
    다른 건 받는 사람뿐이다 — 테스트는 멘션한 사람에게만, 전원 발송은 신청자 전원에게.
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
            self._reply(
                strip_multiline(
                    f"""
                    받을 사람을 같이 멘션해줘! 실수로 신청자 전원에게 나가지 않게 대상 지정을 필수로 해뒀어.
                    예) `{TRIGGER} {TEST_PHRASE} <@{self.user}>`
                    (진짜로 전원에게 보내려면 `{TRIGGER} {BROADCAST_PHRASE}` 라고 해줘!)"""
                )
            )
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
        """멘션된 슬랙 계정들. 자기 자신에게 보내보는 게 정상 사용이라 실행자도 제외하지 않는다."""
        return [
            user_id
            for user_id in SLACK_USER_PAT.findall(self.text)
            if user_id != self.anna_id
        ]

    @staticmethod
    def _build_report(result: ReminderResult, targets) -> str:
        if not result.bigchat_names:
            return strip_multiline(
                f"""
                {result.target_date} 에 시작하는 빅챗을 못 찾았어. 그래서 보낼 것도 없었어.
                - 빅챗 이름 형식(`<이름> yy-MM-DD HH:mm~HH:mm`)으로 읽힌 시트: {result.parsed_sheet_cnt}개
                - 형식이 안 맞아서 무시한 시트: {result.ignored_sheet_cnt}개
                시트 이름이 이 형식인지 확인해줘! 자세한 목록은 로그에 남겼어."""
            )

        found = ", ".join(result.bigchat_names)
        unresolved = result.applicant_cnt - result.resolved_cnt
        unresolved_note = (
            f"\n신청자 {unresolved}명은 멤버 시트에서 슬랙 계정을 못 찾아서 못 보냈어. (누군지는 로그에 남겼어!)"
            if unresolved
            else ""
        )
        if targets is None:
            return strip_multiline(
                f"""
                {result.target_date} 빅챗 `{found}` 신청자들에게 리마인더를 보냈어!
                - 신청 시트에서 찾은 신청자: {result.applicant_cnt}명
                - 실제로 DM 을 보낸 사람: {result.sent_cnt}명{unresolved_note}"""
            )

        target_txt = ", ".join(f"<@{user_id}>" for user_id in targets)
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
