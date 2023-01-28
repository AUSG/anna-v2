import os
import re
import logging
from typing import Union, Optional

from implementation import GoogleSpreadsheetClient, SlackClient

logger = logging.getLogger(__name__)

ANNA_ID = os.environ.get('ANNA_ID')


class WorksheetMaker:
    def __init__(self, slack_client: SlackClient, gs_client: GoogleSpreadsheetClient):
        self.slack_client = slack_client
        self.gs_client = gs_client

    def find_or_create_worksheet(self, ts: str, channel: str, spreadsheet_id: str):
        try:
            worksheet_id: Optional[int] = self.find_worksheet_id_in_thread(ts, channel)

            if worksheet_id:
                is_new = False
            else:
                is_new = True
                worksheet_id = self.create_worksheet_in_spread_sheet(spreadsheet_id)
        except Exception as e:
            logging.error("fail to find_or_create_worksheet", e)
            raise e

        return is_new, worksheet_id

    def create_worksheet_in_spread_sheet(self, spreadsheet_id: str) -> Optional[int]:
        worksheet_id: Optional[int] = self.gs_client.create_worksheet(
            spreadsheet_id=spreadsheet_id,
            title_prefix="[제목바꿔줘]",
            header_values=["타임스탬프", "이메일 주소", "이름", "영문 이름", "휴대폰 번호", "학교명 혹은 회사명"]
        )

        return worksheet_id

    def find_worksheet_id_in_thread(self, ts: str, channel: str) -> Union[int, None]:
        SPREADSHEET_URL_PATTERN = r'https:\/\/docs.google.com\/spreadsheets\/d\/.*\/edit#gid=(\d*)'

        messages = self.slack_client.get_replies(ts, channel)

        for message in messages:
            if message.user == ANNA_ID:
                pat = re.search(SPREADSHEET_URL_PATTERN, message.text)
                if pat is not None and len(pat.groups()) > 0:
                    return int(pat.groups()[0])
        return None
