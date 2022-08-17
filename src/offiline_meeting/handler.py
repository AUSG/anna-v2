import logging
from typing import Dict, Any

import env_bucket
from event import EmojiAddedEvent
from google_spreadsheet_client import GsClient
from member.service import MemberService
from offiline_meeting.service import OmService
from slack_bolt import Say
from slack_client import SlackClient
from slack_sdk import WebClient

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("offline_meeting.handler")

ADMIN_CHANNEL = env_bucket.get('ADMIN_CHANNEL')


class OmHandler:
    def check_and_run(self, web_client: WebClient, say: Say, event: Dict[str, Any]):
        ea_event, om_service, slack_client = self._inject_dependencies(event, say, web_client)

        try:
            is_new, url = om_service.join()
            if is_new is None:
                return
            elif is_new:
                slack_client.send_msg(msg=f"새로운 시트를 만들었어! <{url}|구글스프레드 시트>", ts=ea_event.ts)
                slack_client.send_msg(msg=f"<@{ea_event.slack_unique_id}>, 등록 완료!", ts=ea_event.ts)
            else:
                slack_client.send_msg(msg=f"<@{ea_event.slack_unique_id}>, 등록 완료!", ts=ea_event.ts)
        except Exception as ex:
            self._error_log(ex, ea_event, slack_client)

    def _inject_dependencies(self, event, say, web_client):
        ea_event = EmojiAddedEvent(event['reaction'], event['item']['ts'], event['item']['channel'], event['user'])
        slack_client = SlackClient(web_client, say)
        gs_client = GsClient()
        member_service = MemberService(gs_client)
        om_service = OmService(ea_event, slack_client, member_service, gs_client)

        return ea_event, om_service, slack_client

    def _error_log(self, ex: Exception, ea_event: EmojiAddedEvent, slack_client: SlackClient):
        logging.error(ex)
        slack_client.send_msg(msg=f"엇, <@{ea_event.slack_unique_id}>, 등록에 실패했어. 알아보고 연락줄게!", ts=ea_event.ts)
        slack_client.send_msg(
            msg=f"흠, <@{ea_event.slack_unique_id}> 의 정보를 입력할 수 없었어. 멤버 정보 시트를 확인하고, 직접 시트에 데이터를 추가해 줘.\n"
                f"당사자에게 알려주는 것 잊지 말고!\n\n발생한 에러: {ex.__class__.__name__} - {ex}",
            channel=ADMIN_CHANNEL)
