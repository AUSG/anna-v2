import logging
import re
from typing import List, Optional

from config.env_config import envs
from implementation.member_finder import MemberNotFound, MemberLackInfo
from implementation.slack_client import Message
from urllib.parse import urlencode

from util.bigchat_event import (
    ics_payload,
    ics_token,
    parse_sheet_name,
    to_gcal_link_truncated,
)
from util.utils import strip_multiline

logger = logging.getLogger(__name__)

SPREADSHEET_PAT = re.compile(
    r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
)


class JoinBigchat:
    def __init__(self, event, target_emoji, slack_client, gs_client, member_manager):
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
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

    def _build_calendar_blocks(
        self, msg: str, worksheet_id: int, intro_text: str
    ) -> Optional[List[dict]]:
        """시트 이름에서 이벤트 정보를 파싱해 캘린더 버튼 블록을 만든다. 구형식 시트 등 파싱 불가면 None.

        스레드 첫 글(intro_text)은 캘린더 일정의 본문이 된다 — gcal은 details 파라미터로
        (버튼 url 길이 제한에 맞게 잘라서), ics는 클릭 시점에 서버가 슬랙에서 다시 읽어온다.
        """
        try:
            sheet_name = self.gs_client.get_worksheet_title(worksheet_id)
            event = parse_sheet_name(sheet_name)
        except Exception as ex:
            logger.warning(f"Failed to build calendar buttons: {ex}")
            return None
        if not event:
            return None

        buttons = [
            {
                "type": "button",
                "action_id": "calendar_gcal",
                "text": {
                    "type": "plain_text",
                    "text": "📅 Google Calendar에 추가",
                    "emoji": True,
                },
                "url": to_gcal_link_truncated(event, intro_text),
            }
        ]
        if envs.ICS_TOKEN_SECRET:
            token = ics_token(
                envs.ICS_TOKEN_SECRET,
                ics_payload(worksheet_id, self.channel, self.ts),
            )
            query = urlencode({"token": token, "channel": self.channel, "ts": self.ts})
            buttons.append(
                {
                    "type": "button",
                    "action_id": "calendar_ics",
                    "text": {
                        "type": "plain_text",
                        "text": "📥 .ics 다운로드",
                        "emoji": True,
                    },
                    "url": f"{envs.PUBLIC_BASE_URL}/bigchat/{worksheet_id}/event.ics?{query}",
                }
            )

        return [
            {"type": "section", "text": {"type": "mrkdwn", "text": msg}},
            {"type": "actions", "elements": buttons},
        ]

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
        msg = strip_multiline(
            f"""
            <@{self.user}> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
            ```
            이름(영문): {member.kor_name}({member.eng_name})
            핸드폰: {member.phone}
            이메일: {member.email}
            학교/회사: {member.school_name_or_company_name}
            ```
            (참고로 이 메시지는 너만 볼 수 있어!)"""
        )
        self.slack_client.send_message_only_visible_to_user(
            msg=msg,
            blocks=self._build_calendar_blocks(msg, worksheet_id, messages[0].text),
            channel=self.channel,
            ts=self.ts,
            user_id=self.user,
        )
        return True
