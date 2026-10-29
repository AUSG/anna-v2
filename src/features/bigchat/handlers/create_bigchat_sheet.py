from features.bigchat.models import CreateBigchatCommand, InvalidBigchatName
from features.bigchat.presentation.messages import (
    bigchat_created_message,
    invalid_bigchat_name_message,
)
from features.bigchat.services.creation import register_early_reacted_users
from shared.mention_handler import MentionHandler
from slack_router import matches_mention


class CreateBigchatSheet(MentionHandler):
    def __init__(self, event, slack_client, bigchats, member_manager, target_emoji):
        self.text = event["text"]
        self.ts = event["ts"]
        self.thread_ts = event.get("thread_ts")
        self.channel = event["channel"]
        self.user = event["user"]
        self.slack_client = slack_client
        self.bigchats = bigchats
        self.member_manager = member_manager
        self.target_emoji = target_emoji

    def handle_mention(self):
        if not self.can_handle():
            return False

        sheet_name = (
            self.text.split("새로운 빅챗", maxsplit=1)[1].split("\n")[0].strip()
        )
        try:
            command = CreateBigchatCommand(sheet_name)
        except InvalidBigchatName:
            command = None

        # 전송 오류에 검증 예외가 섞이지 않게 한다.
        if command is None:
            self.slack_client.send_message_only_visible_to_user(
                msg=invalid_bigchat_name_message(self.user),
                channel=self.channel,
                ts=self.ts,
                user_id=self.user,
            )
            return False

        created = self.bigchats.create(
            command.sheet_name,
            channel=self.channel,
            thread_ts=self.thread_ts or self.ts,
        )
        self.slack_client.send_message(
            msg=bigchat_created_message(created.sheet_url, created.sheet_name),
            ts=self.ts,
        )
        register_early_reacted_users(
            self.slack_client,
            self.bigchats,
            self.member_manager,
            self.target_emoji,
            created.worksheet_id,
            channel=self.channel,
            # 모집글(스레드 부모). 스레드 없이 채널에 바로 멘션했다면 멘션 글 자체가 모집글이다.
            thread_ts=self.thread_ts or self.ts,
        )
        return True

    def can_handle(self):
        return matches_mention("create_bigchat", self.text)
