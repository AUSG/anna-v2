import re
from typing import List

from implementation.member_finder import MemberNotFound, MemberLackInfo
from implementation.slack_client import Message

SPREADSHEET_PAT = re.compile(
    r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
)


class AbandonBigchat:
    def __init__(
        self, event, anna, target_emoji, slack_client, member_manager, gs_client
    ):
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

        self.gs_client.delete_row(worksheet_id, member.email)

        self.slack_client.send_message_only_visible_to_user(
            msg=f"<@{self.user}>, 등록을 취소했어.",
            channel=self.channel,
            ts=self.ts,
            user_id=self.user,
        )
        return True
