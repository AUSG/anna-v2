import re
from contextlib import nullcontext
from typing import List

from implementation.google_spreadsheet_client import WorksheetNotFound
from implementation.member_finder import MemberNotFound, MemberLackInfo
from implementation.slack_client import Message

SPREADSHEET_PAT = re.compile(
    r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
)


class AbandonBigchat:
    def __init__(
        self,
        event,
        anna,
        target_emoji,
        slack_client,
        member_manager,
        gs_client,
        loading_emoji=None,
    ):
        """loading_emoji: 실제 취소 작업만 감쌀 컨텍스트 매니저. 넘기지 않으면 이모지를 붙이지 않는다."""
        self.anna = anna
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.target_emoji = target_emoji
        self.slack_client = slack_client
        self.member_manager = member_manager
        self.gs_client = gs_client
        self.loading_emoji = loading_emoji or nullcontext()

    @staticmethod
    def _extract_worksheet_id(messages: List[Message]):
        for message in messages:
            pat = SPREADSHEET_PAT.search(message.text)
            if pat is not None and len(pat.groups()) > 0:
                return int(pat.groups()[0])
        return None

    def run(self):
        if self.type != "reaction_removed" or self.reaction != self.target_emoji:
            return False

        messages = self.slack_client.get_replies(channel=self.channel, ts=self.ts)
        if messages[0].ts != self.ts:
            return False

        worksheet_id = self._extract_worksheet_id(messages)
        if not worksheet_id:
            return False

        # 여기부터가 실제 동작이다. 위 검사들에서 걸러진 이벤트(관심 없는 이모지, 빅챗 글이
        # 아닌 메시지 등)에는 loading 이모지가 아예 붙지 않는다.
        with self.loading_emoji:
            return self._abandon(worksheet_id)

    def _abandon(self, worksheet_id: int) -> bool:
        try:
            member = self.member_manager.find(self.user)
        except MemberNotFound:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 네 정보를 찾지 못했어.", ts=self.ts
            )
            return False
        except MemberLackInfo:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 네 정보에 누락된 값이 있어.", ts=self.ts
            )
            return False

        try:
            self.gs_client.delete_row(worksheet_id, member.email)
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
