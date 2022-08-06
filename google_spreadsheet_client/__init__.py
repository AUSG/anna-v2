import logging
from datetime import datetime
from typing import List

import gspread
from dateutil.tz import gettz
from gspread_formatting import set_column_width

import env_bucket

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("google_spreadsheet_client")

FORM_SPREADSHEET_ID = env_bucket.get('FORM_SPREADSHEET_ID')


class GsClient:
    def __init__(self):
        self.gs_client = gspread.service_account(filename='./gcp_serviceaccount_secret.json')

    def create_worksheet(self) -> int:
        spreadsheet = self.gs_client.open_by_key(FORM_SPREADSHEET_ID)

        now = self._get_now().strftime('%Y/%m/%d-%H%M%S')
        worksheet = spreadsheet.add_worksheet(f"[제목고쳐줘] {now}", rows=100, cols=30)
        worksheet.append_row(["타임스탬프", "이메일 주소", "이름", "영문 이름", "휴대폰 번호", "학교명 혹은 회사명"])
        set_column_width(worksheet, 'A:F', 220)

        return worksheet.id

    def append_row(self, worksheet_id: int, values: List[str]):
        worksheet = self._get_worksheet(worksheet_id)

        now = str(self._get_now())
        worksheet.append_row([now, *values])

    def get_values(self, worksheet_id: int, cell_range: str) -> List[List[str]]:
        members_worksheet = self._get_worksheet(worksheet_id)
        return members_worksheet.get_values(cell_range)

    def generate_url(self, worksheet_id: int) -> str:
        return f"https://docs.google.com/spreadsheets/d/{FORM_SPREADSHEET_ID}/edit#gid={worksheet_id}"

    def _get_worksheet(self, worksheet_id: int):
        spreadsheet = self.gs_client.open_by_key(FORM_SPREADSHEET_ID)
        members_worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
        return members_worksheet

    def _get_now(self):
        return datetime.now(gettz('Asia/Seoul'))  # UTC+9
