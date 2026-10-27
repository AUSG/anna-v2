import logging
from contextlib import nullcontext
from typing import List, Optional

from config.env_config import envs
from features.bigchat.presentation.messages import build_registration_info_message
from features.bigchat.services.sheet_link import extract_worksheet_id
from integrations.google_sheets import WorksheetNotFound
from features.members.services.directory import MemberNotFound, MemberLackInfo
from integrations.slack import Message
from urllib.parse import urlencode

from features.bigchat.calendar import (
    calendar_payload,
    calendar_token,
    parse_sheet_name,
    to_gcal_link_truncated,
)

logger = logging.getLogger(__name__)


class JoinBigchat:
    def __init__(
        self,
        event,
        target_emoji,
        slack_client,
        gs_client,
        member_manager,
        loading_emoji=None,
        *,
        settings=envs,
    ):
        """loading_emoji: 실제 등록 작업만 감쌀 컨텍스트 매니저. 넘기지 않으면 이모지를 붙이지 않는다."""
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.target_emoji = target_emoji
        self.settings = settings
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.loading_emoji = loading_emoji or nullcontext()

    def _build_calendar_blocks(
        self, msg: str, worksheet_id: int, intro_text: str
    ) -> Optional[List[dict]]:
        """시트 이름에서 이벤트 정보를 파싱해 캘린더 버튼 블록을 만든다. 구형식 시트 등 파싱 불가면 None.

        gcal 버튼은 캘린더 템플릿 URL을 직접 사용한다. 서버의 302 리다이렉트를 거치면
        모바일 앱으로 연결되지 않고 로그아웃된 웹뷰가 열려 구글 마케팅 페이지로 이동한다.
        Slack 버튼 URL은 3000자까지 허용하므로 긴 소개글은 전부 넣을 수 없다.
        gcal 본문에는 원본 메시지의 permalink를 먼저 넣고 그 아래에 소개글을 붙인다.
        소개글은 뒤에서부터 잘라 permalink가 먼저 유지되도록 한다.
        ics에는 서버가 클릭 시점에 읽은 소개글 전문을 넣는다.
        """
        try:
            sheet_name = self.gs_client.get_worksheet_title(worksheet_id)
            event = parse_sheet_name(sheet_name)
        except Exception as ex:
            logger.warning(f"Failed to build calendar buttons: {ex}")
            return None
        if not event:
            return None

        permalink = self.slack_client.get_permalink(self.channel, self.ts)
        gcal_details = (
            f"슬랙에서 소개글 보기: {permalink}\n\n{intro_text}" if permalink else intro_text
        )
        buttons = [
            {
                "type": "button",
                "action_id": "calendar_gcal",
                "text": {
                    "type": "plain_text",
                    "text": "📅 Google Calendar에 추가",
                    "emoji": True,
                },
                "url": to_gcal_link_truncated(event, gcal_details),
            }
        ]
        if self.settings.ICS_TOKEN_SECRET:
            token = calendar_token(
                self.settings.ICS_TOKEN_SECRET,
                calendar_payload(worksheet_id, self.channel, self.ts),
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
                    "url": f"{self.settings.PUBLIC_BASE_URL}/bigchat/{worksheet_id}/event.ics?{query}",
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

        worksheet_id = extract_worksheet_id(message.text for message in messages)
        if not worksheet_id:
            return False

        # 여기부터가 실제 동작이다. 위 검사들에서 걸러진 이벤트(관심 없는 이모지, 빅챗 글이
        # 아닌 메시지 등)에는 loading 이모지가 아예 붙지 않는다.
        with self.loading_emoji:
            return self._register(worksheet_id, messages)

    def _register(self, worksheet_id: int, messages: List[Message]) -> bool:
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

        try:
            added = self.gs_client.append_row_if_absent(
                worksheet_id, member.transform_for_spreadsheet()
            )
        except WorksheetNotFound:
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 이 빅챗의 신청 시트를 찾을 수 없어. 이미 마감되었거나 삭제된 것 같아. "
                f"모집이 진행 중인 빅챗이라면 운영진에게 알려줘!",
                ts=self.ts,
            )
            return False

        if not added:
            # 시트 생성 직후의 일괄 등록(#89)과 동시에 처리됐거나 이벤트가 중복 전달된 경우
            self.slack_client.send_message(
                msg=f"<@{self.user}>, 이미 등록되어 있어!", ts=self.ts
            )
            return True

        self.slack_client.send_message(msg=f"<@{self.user}>, 등록 완료!", ts=self.ts)
        msg = build_registration_info_message(self.user, member)
        self.slack_client.send_message_only_visible_to_user(
            msg=msg,
            blocks=self._build_calendar_blocks(msg, worksheet_id, messages[0].text),
            channel=self.channel,
            ts=self.ts,
            user_id=self.user,
        )
        return True
