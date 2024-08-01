from typing import List
import re
import textwrap

from implementation.member_finder import MemberNotFound, MemberLackInfo
from implementation.slack_client import Message


SPREADSHEET_PAT = re.compile(
    r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
)


class JoinBigchat:
    def __init__(self, event, target_emoji, slack_client, gs_client, member_manager):
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.item_user = event["item_user"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.target_emoji = target_emoji
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager

    @staticmethod
    def _extract_worksheet_id(messages: List[Message]):
        for message in messages:
            pat = SPREADSHEET_PAT.search(message.text)
            if pat is not None and len(pat.groups()) > 0:
                return int(pat.groups()[0])
        return None

    def run(self):
        if self.type != "reaction_added" or self.reaction != self.target_emoji:
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
                msg=f"<@{self.user}>, 네 정보를 찾지 못했어. 운영진에게 연락해줘!", ts=self.ts
            )
            return False
        except MemberLackInfo:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 네 정보에 누락된 값이 있어. 운영진에게 연락해줘!", ts=self.ts
            )
            return False

        self.gs_client.append_row(worksheet_id, member.transform_for_spreadsheet())

        self.slack_client.send_message(msg=f"<@{self.user}>, 등록 완료!", ts=self.ts)
        self.slack_client.send_message_only_visible_to_user(
            msg=textwrap.dedent(
                f"""
                <@{self.user}> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
                ```
                이름(영문): {member.kor_name}({member.eng_name})
                핸드폰: {member.phone}
                이메일: {member.email}
                학교/회사: {member.school_name_or_company_name}
                ```
                (참고로 이 메시지는 너만 볼 수 있어!)
                """
            ),
            channel=self.channel,
            ts=self.ts,
            user_id=self.user,
        )
        return True
