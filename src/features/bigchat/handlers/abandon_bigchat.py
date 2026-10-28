from contextlib import nullcontext

from integrations.google_sheets import WorksheetNotFound


class AbandonBigchat:
    def __init__(
        self,
        event,
        target_emoji,
        slack_client,
        gs_client,
        loading_emoji=None,
    ):
        """loading_emoji: 실제 취소 작업만 감쌀 컨텍스트 매니저. 넘기지 않으면 이모지를 붙이지 않는다."""
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.target_emoji = target_emoji
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.loading_emoji = loading_emoji or nullcontext()

    def run(self):
        if self.type != "reaction_removed" or self.reaction != self.target_emoji:
            return False

        worksheet_id = self.gs_client.find_bigchat(
            channel=self.channel, thread_ts=self.ts
        )
        if worksheet_id is None:
            return False

        # 여기부터가 실제 동작이다. 위 검사들에서 걸러진 이벤트(관심 없는 이모지, 빅챗 글이
        # 아닌 메시지 등)에는 loading 이모지가 아예 붙지 않는다.
        with self.loading_emoji:
            return self._abandon(worksheet_id)

    def _abandon(self, worksheet_id: int) -> bool:
        try:
            self.gs_client.cancel_bigchat(
                worksheet_id, self.user, channel=self.channel, thread_ts=self.ts
            )
        except WorksheetNotFound:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 이 빅챗의 신청 시트를 찾을 수 없어서 등록을 취소하지 못했어. "
                f"이미 마감되었거나 삭제된 것 같아. 필요하면 운영진에게 알려줘!",
                ts=self.ts,
            )
            return False

        self.slack_client.send_message_only_visible_to_user(
            msg=f"<@{self.user}>, 등록을 취소했어.",
            channel=self.channel,
            ts=self.ts,
            user_id=self.user,
        )
        return True
