import os
import re
import logging
import threading
import time
from typing import Union

from implementation import GoogleSpreadsheetClient, SlackClient

logger = logging.getLogger(__name__)

ANNA_ID = os.environ.get('ANNA_ID')

SINGLE_LOCK = threading.Lock()

class WorksheetMaker:
    def __init__(self, slack_client: SlackClient, gs_client: GoogleSpreadsheetClient):
        self.slack_client = slack_client
        self.gs_client = gs_client

    def find_or_create_worksheet(self, ts: str, channel: str, spreadsheet_id: str):
        try:
            SINGLE_LOCK.acquire()
            time.sleep(3) # TODO [seonghyeok] 더 엘레강스한 방법 찾기. 현재로선 이렇게 해서 "ANNA 가 해당 쓰레드에 worksheet_id 를 남길때까지" 시간을 벌고 있다. 죄악감이 든다.
            worksheet_id = self._find_worksheet_id_in_thread(ts, channel)

            if worksheet_id:
                is_new = False
            else:
                is_new = True
                worksheet_id = self.gs_client.create_worksheet(
                    spreadsheet_id=spreadsheet_id,
                    title_prefix="[제목바꿔줘]",
                    header_values=["타임스탬프", "이메일 주소", "이름", "영문 이름", "휴대폰 번호", "학교명 혹은 회사명"]
                )
        except Exception as e:
            logging.error("fail to find_or_create_worksheet", e)
            raise e
        finally:
            SINGLE_LOCK.release()
        return is_new, worksheet_id

    def _find_worksheet_id_in_thread(self, ts: str, channel: str) -> Union[int, None]:
        SPREADSHEET_URL_PATTERN = r'https:\/\/docs.google.com\/spreadsheets\/d\/.*\/edit#gid=(\d*)'

        messages = self.slack_client.get_replies(ts, channel)

        for message in messages:
            if message.user == ANNA_ID:
                pat = re.search(SPREADSHEET_URL_PATTERN, message.text)
                if pat is not None and len(pat.groups()) > 0:
                    return int(pat.groups()[0])
        return None
