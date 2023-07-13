import re
from typing import List

from config.env_config import envs
from handler.decorator import catch_global_error
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from implementation.member_finder import MemberManager, MemberNotFound, MemberLackInfo
from implementation.slack_client import SlackClient, Message
from util.utils import strip_multiline

MEMBER_MANAGER = None
SPREADSHEET_PAT = re.compile(
    r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
)


def _get_member_manager():  # TODO(seonghyeok): we need better singleton
    global MEMBER_MANAGER
    if not MEMBER_MANAGER:
        MEMBER_MANAGER = MemberManager(GoogleSpreadsheetClient())
    return MEMBER_MANAGER


class AttendBigchat:
    def __init__(self, event, anna, target_emoji, slack_client, member_manager):
        self.anna = anna
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.item_user = event["item_user"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.target_emoji = target_emoji
        self.slack_client = slack_client
        self.member_manager = member_manager

    def _extract_worksheet_id(self, messages: List[Message]):
        """
        return 0 if not found
        """
        for message in messages:
            pat = SPREADSHEET_PAT.search(message.text)
            if pat is not None and len(pat.groups()) > 0:
                return int(pat.groups()[0])
        return 0

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
                msg=f"<@{self.user}>, 네 정보를 찾지 못했어.", ts=self.ts
            )
            return False
        except MemberLackInfo:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 네 정보에 누락된 값이 있어.", ts=self.ts
            )
            return False

        self.member_manager.add_member_to_bigchat_worksheet(member, worksheet_id)

        self.slack_client.send_message(msg=f"<@{self.user}>, 등록 완료!", ts=self.ts)
        self.slack_client.send_message_only_visible_to_user(
            msg=strip_multiline(
                f"""
                <@{self.user}> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
                ```
                핸드폰: {member.phone}
                이메일: {member.email}
                학교/회사: {member.school_name_or_company_name}
                ```
                (참고로 이 메시지는 너만 볼 수 있어!)"""
            ),
            channel=self.channel,
            thread_ts=self.ts,
            user_id=self.user,
        )
        return True


## reaction_added event sample:
# {
#   'type': 'reaction_added',
#   'user': 'UQJ8HQJG5',
#   'reaction': 'kirbyok',
#   'item': {
#     'type': 'message',
#     'channel': 'C03SZTDEDK3',
#     'ts': '1688801145.307229'
#   },
#   'item_user': 'UQJ8HQJG5',
#   'event_ts': '1688833113.003600'
# }
@catch_global_error()
def attend_bigchat(event, say, client):
    AttendBigchat(
        event,
        envs.ANNA_ID,
        envs.JOIN_BIGCHAT_EMOJI,
        SlackClient(say, client),
        _get_member_manager(),
    ).run()


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

    def _extract_worksheet_id(self, messages: List[Message]):
        """
        return 0 if not found
        """
        for message in messages:
            pat = SPREADSHEET_PAT.search(message.text)
            if pat is not None and len(pat.groups()) > 0:
                return int(pat.groups()[0])
        return 0

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

        self.slack_client.send_message(msg=f"<@{self.user}>, 등록을 취소했어.", ts=self.ts)
        return True


@catch_global_error()
def abandon_bigchat(event, say, client):
    AbandonBigchat(
        event,
        envs.ANNA_ID,
        envs.JOIN_BIGCHAT_EMOJI,
        SlackClient(say, client),
        _get_member_manager(),
        GoogleSpreadsheetClient(),
    ).run()


class CreateBigchatSheet:
    def __init__(self, event, slack_client, gs_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client
        self.gs_client = gs_client

    def run(self):
        text = self.text.replace("<@U01BN035Y6L> ", "").strip()
        if "새로운 빅챗" not in text:
            return False

        sheet_name = text.split("새로운 빅챗", maxsplit=1)[1].split("\n")[0].strip()
        if not sheet_name:
            self.slack_client.send_message(msg="시트 이름이 입력되지 않았어. 다시 입력해줘!", ts=self.ts)
            return False

        worksheet_id = self.gs_client.create_bigchat_sheet(sheet_name)
        sheet_url = self.gs_client.get_url(worksheet_id)
        self.slack_client.send_message(
            msg=f"새로운 빅챗, 등록 완료! <{sheet_url}|{sheet_name}> :google_spreadsheets:",
            ts=self.ts,
        )
        return True


## app_mention event sample:
# {
#     'client_msg_id': '8fb50d48-f93d-4cca-b9ca-6965479e9a93',
#     'type': 'app_mention',
#     'text': msg,
#     'user': 'UQJ8HQJG5',
#     'ts': '1689403771.805849',
#     'blocks': [ ... ],  # not used and too long, so skipped
#     'team': 'TQLEG4B38',
#     'thread_ts': '1689403100.222939',
#     'parent_user_id': 'UQJ8HQJG5',
#     'channel': 'C03SZTDEDK3',
#     'event_ts': '1689403771.805849'
# }
@catch_global_error()
def create_bigchat_sheet(event, say, client):
    CreateBigchatSheet(event, SlackClient(say, client), GoogleSpreadsheetClient()).run()


class SimpleResponse:
    def __init__(self, event, slack_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.slack_client = slack_client

    def run(self):
        text = self.text.replace("<@U01BN035Y6L>", "").strip()
        if text:
            return False

        self.slack_client.send_message(msg="?", ts=self.ts)
        return True


@catch_global_error()
def simple_response(event, say, client):
    SimpleResponse(event, SlackClient(say, client)).run()
