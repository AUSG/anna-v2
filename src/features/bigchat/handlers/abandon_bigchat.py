from contextlib import nullcontext

from features.bigchat.errors import BigchatError, ReactionSuperseded
from features.bigchat.presentation.messages import bigchat_storage_error_message
from features.bigchat.services.lookup import find_bigchat


class AbandonBigchat:
    def __init__(
        self,
        event,
        target_emoji,
        slack_client,
        bigchats,
        loading_emoji=None,
    ):
        """loading_emoji: 실제 취소 작업만 감쌀 컨텍스트 매니저. 넘기지 않으면 이모지를 붙이지 않는다."""
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.event_ts = event.get("event_ts")
        self.target_emoji = target_emoji
        self.slack_client = slack_client
        self.bigchats = bigchats
        self.loading_emoji = loading_emoji or nullcontext()

    def run(self):
        if self.type != "reaction_removed" or self.reaction != self.target_emoji:
            return False

        try:
            return self._run()
        except ReactionSuperseded:
            return False
        except BigchatError as error:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, {bigchat_storage_error_message(error, '취소')}",
                ts=self.ts,
            )
            return False

    def _run(self):
        worksheet_id = find_bigchat(
            self.slack_client, self.bigchats, channel=self.channel, ts=self.ts
        )
        if worksheet_id is None:
            return False

        # 여기부터가 실제 동작이다. 위 검사들에서 걸러진 이벤트(관심 없는 이모지, 빅챗 글이
        # 아닌 메시지 등)에는 loading 이모지가 아예 붙지 않는다.
        with self.loading_emoji:
            return self._abandon(worksheet_id)

    def _abandon(self, worksheet_id: int) -> bool:
        cancelled = self.bigchats.cancel(
            worksheet_id,
            self.user,
            channel=self.channel,
            thread_ts=self.ts,
            event_ts=self.event_ts,
        )

        # 신청 기록이 없으면(등록에 실패했거나 이미 취소된 경우) 취소했다고 알리지 않는다.
        msg = "등록을 취소했어." if cancelled else "취소할 신청 기록이 없어."
        self.slack_client.send_message_only_visible_to_user(
            msg=f"<@{self.user}>, {msg}",
            channel=self.channel,
            ts=self.ts,
            user_id=self.user,
        )
        return True
