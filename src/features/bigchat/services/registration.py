from contextlib import nullcontext
from typing import List, Optional

from features.bigchat.presentation.messages import build_registration_info_message
from features.bigchat.services.calendar import build_registration_calendar_blocks
from features.bigchat.services.sheet_link import extract_worksheet_id
from integrations.google_sheets import WorksheetNotFound
from features.members.models import MemberNotFound, MemberLackInfo
from integrations.slack import Message


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
        public_base_url: str,
        token_secret: str,
    ):
        """loading_emoji: 실제 등록 작업만 감쌀 컨텍스트 매니저. 넘기지 않으면 이모지를 붙이지 않는다."""
        self.type = event["type"]
        self.reaction = event["reaction"]
        self.channel = event["item"]["channel"]
        self.ts = event["item"]["ts"]
        self.user = event["user"]
        self.target_emoji = target_emoji
        self.slack_client = slack_client
        self.gs_client = gs_client
        self.member_manager = member_manager
        self.loading_emoji = loading_emoji or nullcontext()
        self.public_base_url = public_base_url
        self.token_secret = token_secret

    @staticmethod
    def _extract_worksheet_id(messages: List[Message]):
        return extract_worksheet_id(message.text for message in messages)

    def _build_calendar_blocks(
        self, msg: str, worksheet_id: int, intro_text: str
    ) -> Optional[List[dict]]:
        return build_registration_calendar_blocks(
            msg,
            worksheet_id,
            intro_text,
            self.channel,
            self.ts,
            self.slack_client,
            self.gs_client,
            public_base_url=self.public_base_url,
            token_secret=self.token_secret,
        )

    def run(self):
        if self.type != "reaction_added" or self.reaction != self.target_emoji:
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
            # 일괄 등록과 동시에 처리됐거나 이벤트가 중복 전달된 경우
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
