import logging

from slack_sdk.errors import SlackApiError

from handler.bigchat.join_bigchat import build_registration_info_message
from handler.bigchat.mention_handler import MentionHandler
from implementation.member_finder import MemberLackInfo, MemberNotFound
from util.bigchat_event import parse_sheet_name
from util.utils import strip_multiline

logger = logging.getLogger(__name__)


class CreateBigchatSheet(MentionHandler):
    def __init__(self, event, slack_client, gs_client, member_manager, target_emoji):
        self.text = event["text"]
        self.ts = event["ts"]
        self.thread_ts = event.get("thread_ts")
        self.channel = event["channel"]
        self.user = event["user"]
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.target_emoji = target_emoji

    def handle_mention(self):
        if not self.can_handle():
            return False

        sheet_name = self.text.split("새로운 빅챗", maxsplit=1)[1].split("\n")[0].strip()
        if not parse_sheet_name(sheet_name):
            self.slack_client.send_message_only_visible_to_user(
                msg=strip_multiline(
                    f"""
                    <@{self.user}> 형식이 올바르지 않아서 빅챗을 만들지 않았어. 아래 형식으로 다시 입력해줘!
                    `새로운 빅챗 <이름> yy-MM-DD HH:mm~HH:mm`
                    예) `새로운 빅챗 AI 밋업 26-08-20 19:00~21:00`
                    (실제 존재하는 날짜/시각이어야 하고, 종료 시각은 시작보다 늦어야 해!)"""
                ),
                channel=self.channel,
                ts=self.ts,
                user_id=self.user,
            )
            return False

        worksheet_id = self.gs_client.create_bigchat_sheet(sheet_name)
        sheet_url = self.gs_client.get_url(worksheet_id)
        self.slack_client.send_message(
            msg=f"새로운 빅챗, 등록 완료! <{sheet_url}|{sheet_name}> :google_spreadsheets:",
            ts=self.ts,
        )
        self._register_early_reacted_users(worksheet_id)
        return True

    def can_handle(self):
        return "새로운 빅챗" in self.text

    def _register_early_reacted_users(self, worksheet_id):
        """시트가 생기기 전에 모집글에 :gogo:를 눌러 등록되지 못한 사람들을 일괄 등록한다. (#89)

        reaction 은 시트 링크 메시지를 올린 '뒤에' 읽는다. 링크가 올라간 이후의
        reaction 은 JoinBigchat(reaction_added)이 정상 처리하므로, 이 순서면 시트
        생성 전후 어느 시점에 눌린 reaction 도 두 경로 중 한쪽에는 반드시 잡힌다.
        두 경로가 거의 동시에 같은 사람을 처리해도 append_row_if_absent 가
        중복 등록을 막는다.

        여기 도달했다면 시트 생성과 링크 안내는 이미 성공했으므로, 일괄 등록이
        실패해도 전체 요청을 실패 처리하면 안 된다 — 전역 에러 핸들러의
        '다시 시도해줘' 안내를 따라 멘션을 다시 보내면 같은 이름의 시트를 또
        만들려다 실패한다. 대신 스레드에 경고만 남긴다.
        """
        # 모집글(스레드 부모)에 달린 reaction 을 읽어야 한다. 스레드 없이 채널에
        # 바로 멘션한 경우엔 멘션 글 자체가 모집글이다.
        parent_ts = self.thread_ts or self.ts
        reaction = self.slack_client.get_emoji(
            channel=self.channel, ts=parent_ts, emoji_name=self.target_emoji
        )
        if reaction is None:
            return

        try:
            registered = []
            for user in reaction.users:
                try:
                    member = self.member_manager.find(user)
                except MemberNotFound:
                    self.slack_client.send_message(
                        msg=f"<@{user}>, 네 정보를 찾지 못했어. 운영진에게 연락해줘!",
                        ts=self.ts,
                    )
                except MemberLackInfo:
                    self.slack_client.send_message(
                        msg=f"<@{user}>, 네 정보에 누락된 값이 있어. 운영진에게 연락해줘!",
                        ts=self.ts,
                    )
                else:
                    if self.gs_client.append_row_if_absent(
                        worksheet_id, member.transform_for_spreadsheet()
                    ):
                        registered.append((user, member))

            if not registered:
                return

            mentions = " ".join(f"<@{user}>" for user, _ in registered)
            self.slack_client.send_message(
                msg=f"{mentions} 시트가 만들어지기 전에 :{self.target_emoji}:를 눌러줬구나! 지금 등록 완료했어!",
                ts=self.ts,
            )
            for user, member in registered:
                try:
                    self.slack_client.send_message_only_visible_to_user(
                        msg=build_registration_info_message(user, member),
                        channel=self.channel,
                        ts=self.ts,
                        user_id=user,
                    )
                except SlackApiError as ex:
                    # 채널을 떠났거나 비활성화된 반응자에게는 ephemeral 을 못 보낸다.
                    # 등록 자체는 이미 끝났으므로 나머지 인원 안내를 계속한다.
                    logger.warning(
                        f"Failed to send registration info to {user}: {ex}"
                    )
        except Exception:
            logger.exception("Failed to backfill early reactions")
            self.slack_client.send_message(
                msg=f"미리 눌린 :{self.target_emoji}: 자동 등록을 처리하다 문제가 생겨서 멈췄어. "
                "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!",
                ts=self.ts,
            )
