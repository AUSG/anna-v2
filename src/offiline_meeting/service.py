import logging
import re

import env_bucket
from event import EmojiAddedEvent
from google_spreadsheet_client import GsClient
from member.service import MemberService
from slack_client import SlackClient

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("offline_meeting.service")

ANNOUNCEMENT_CHANNEL_ID = env_bucket.get('ANNOUNCEMENT_CHANNEL_ID')
ANNA_ID = env_bucket.get('ANNA_ID')
SUBMIT_FORM_EMOJI = env_bucket.get('SUBMIT_FORM_EMOJI')

SPREADSHEET_URL_PATTERN = r'https:\/\/docs.google.com\/spreadsheets\/d\/.*\/edit#gid=(\d*)'


class OmService:
    def __init__(self, ea_event: EmojiAddedEvent,
                 slack_client: SlackClient, member_service: MemberService, gs_client: GsClient):
        self.ea_event = ea_event
        self.slack_client = slack_client
        self.member_service = member_service
        self.gs_client = gs_client

    def is_target(self):
        if (self.ea_event.reaction != SUBMIT_FORM_EMOJI or
                self.ea_event.channel != ANNOUNCEMENT_CHANNEL_ID or
                self._is_reply_in_thread()):
            return False
        else:
            return True

    def join(self):
        is_new, worksheet_id = self._get_worksheet_id()
        self.member_service.submit_form(slack_unique_id=self.ea_event.slack_unique_id,
                                        worksheet_id=worksheet_id)
        return is_new, self.gs_client.generate_url(worksheet_id)  # TODO [seonghyeok] 적절한 객체로 바꿔 전달하기 (is_new, url)

    def _is_reply_in_thread(self):
        """
        [CAVEAT] default 값이 해당 쓰레드의 메시지 1000 개를 가져오는 것인데,
            혹시라도 쓰레드의 댓글이 첫 글 포함 1000개가 넘을경우 먼저 작성된 1000개를 가져올지, 나중에 작성된 1000개를 가져올지에 대해 체크해보지 않음.
            만약 후자일 경우 이 코드가 쓰레드의 제일 첫번째 메시지를 가져올 수 있도록 수정해야 함
        """
        resp = self.slack_client.get_replies(ts=self.ea_event.ts, channel=self.ea_event.channel)
        first_msg = resp['messages'][0]

        if 'thread_ts' not in first_msg:  # 아직 댓글이 하나도 없음
            return False
        elif first_msg['thread_ts'] == first_msg['ts']:  # 해당 쓰레드의 첫 번째 글임
            return False
        else:
            return True

    def _get_worksheet_id(self):
        worksheet_id = self._find_worksheet_id_in_thread()
        if worksheet_id is not None:
            return False, worksheet_id  # (is_new, id)
        else:
            return True, self.gs_client.create_worksheet()  # (is_new, id)

    def _find_worksheet_id_in_thread(self):
        response = self.slack_client.get_replies(ts=self.ea_event.ts, channel=self.ea_event.channel)
        for message in response['messages']:
            if message['user'] == ANNA_ID:
                pat = re.search(SPREADSHEET_URL_PATTERN, message['text'])
                if pat is not None and len(pat.groups()) > 0:
                    return int(pat.groups()[0])
        return None
