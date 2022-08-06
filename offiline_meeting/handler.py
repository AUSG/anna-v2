import logging
from typing import Dict, Any

from slack_bolt import Say
from slack_sdk import WebClient

import env_bucket
from event import EmojiAddedEvent
from google_spreadsheet_client import GsClient
from member.service import MemberService
from offiline_meeting.service import OmService
from slack_client import SlackClient

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("offline_meeting.handler")

ADMIN_CHANNEL = env_bucket.get('ADMIN_CHANNEL')

_member_client_cache = None


class OmHandler:
    def check_and_run(self, web_client: WebClient, say: Say, event: Dict[str, Any]):
        ea_event, om_service, slack_client = self._inject_dependencies(event, say, web_client)

        try:
            if om_service.is_target():
                is_new, url = om_service.join()
                if is_new:
                    slack_client.send_msg(msg=f"새로운 시트를 만들었어! <{url}|구글스프레드 시트>", ts=ea_event.ts)
                slack_client.send_msg(msg=f"<@{ea_event.slack_unique_id}>, 등록 완료!", ts=ea_event.ts)
        except Exception as ex:
            logging.error(str(ex))
            logging.error(ex)
            # TODO [seonghyeok]: __all_field_filled 를 커버하는 별도의 exception 추가
            slack_client.send_msg(msg=f"엇, <@{ea_event.slack_unique_id}>, 등록에 실패했어. 알아보고 연락줄게!", ts=ea_event.ts)
            slack_client.send_msg(
                msg=f"흠, <@{ea_event.slack_unique_id}> 의 정보를 입력할 수 없었어. 멤버 정보 시트를 확인하고, 직접 시트에 데이터를 추가해 줘. 당사자에게 알려주는 것 잊지 말고!",
                channel=ADMIN_CHANNEL)

    def _inject_dependencies(self, event, say, web_client):
        global _member_client_cache

        ea_event = EmojiAddedEvent(event['reaction'], event['item']['ts'], event['item']['channel'], event['user'])

        slack_client = SlackClient(web_client, say)

        gs_client = GsClient()

        if _member_client_cache is None:
            _member_client_cache = MemberService(gs_client)
        member_service = _member_client_cache

        om_service = OmService(ea_event, slack_client, member_service, gs_client)

        return ea_event, om_service, slack_client
