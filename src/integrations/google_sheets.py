"""SheetsGateway 의 gspread 구현."""

import logging
import threading
from datetime import datetime
from typing import List, Optional, Tuple

from dateutil.tz import gettz
from gspread import service_account_from_dict, Worksheet, Spreadsheet
from gspread.exceptions import WorksheetNotFound
from gspread_formatting import set_column_width

from config.env_config import Settings
from shared.gateways import AppendOutcome
from shared.retry import retry

# append_row_if_absent 의 확인-후-추가를 원자적으로 만드는 프로세스 전역 락.
# 이 앱은 단일 프로세스(gunicorn --workers 1)로 떠 있어서 프로세스 락으로 충분하다.
_APPEND_IF_ABSENT_LOCK = threading.Lock()


class GoogleSpreadsheetClient:
    def __init__(self, settings: Settings):
        self.logger = logging.getLogger(__name__)
        self.gs_client = service_account_from_dict(settings.gcp_service_account())
        self.spreadsheet_id = settings.FORM_SPREADSHEET_ID

    def _create_worksheet(
        self,
        title: str = None,
        header_values: List[str] = None,
        row_size: int = 100,
        col_size: int = 30,
        col_width: int = 220,
    ) -> int:
        if not header_values:
            header_values = []
        if not title:
            title = f"[NoName] {self._yyyymmddhhmmss()}"

        spreadsheet = self._get_spreadsheet()

        worksheet = spreadsheet.add_worksheet(
            title, rows=row_size, cols=col_size, index=3
        )  # index is 0-based
        worksheet.append_row(header_values)
        set_column_width(
            worksheet, self._convert_list_to_sheet_range(len(header_values)), col_width
        )

        return worksheet.id

    def append_row(
        self,
        worksheet_id: int,
        values: List[str],
        timestamp_on_first_row: bool = False,
    ):
        def _append():
            _values = list(values)
            worksheet = self._get_worksheet(worksheet_id)
            if timestamp_on_first_row:
                _values.insert(0, self._yyyymmddhhmmss())
            worksheet.append_row(_values)

        retry(_append, non_retryable=(WorksheetNotFound,))

    def append_row_if_absent(
        self, worksheet_id: int, values: List[str]
    ) -> AppendOutcome:
        """같은 행이 이미 있으면 추가하지 않는다.

        빅챗 등록은 반응 이벤트와 시트 생성 직후의 일괄 등록이 거의 동시에 같은
        사람을 처리할 수 있어서, 확인과 추가를 프로세스 전역 락으로 직렬화한다.
        """
        with _APPEND_IF_ABSENT_LOCK:
            try:
                if list(values) in self._values(worksheet_id):
                    return AppendOutcome.ALREADY_PRESENT
                self.append_row(worksheet_id, values)
            except WorksheetNotFound:
                return AppendOutcome.WORKSHEET_MISSING
            return AppendOutcome.ADDED

    def _values(self, worksheet_id: int, cell_range=None) -> List[List[str]]:
        return retry(
            lambda: self._get_worksheet(worksheet_id).get_values(cell_range),
            non_retryable=(WorksheetNotFound,),
        )

    def get_values(self, worksheet_id: int, cell_range=None) -> List[List[str]]:
        try:
            return self._values(worksheet_id, cell_range)
        except WorksheetNotFound:
            return []

    def get_worksheet_title(self, worksheet_id: int) -> Optional[str]:
        try:
            return retry(
                lambda: self._get_worksheet(worksheet_id).title,
                non_retryable=(WorksheetNotFound,),
            )
        except WorksheetNotFound:
            return None

    def list_worksheets(self) -> List[Tuple[int, str]]:
        """스프레드시트의 모든 워크시트를 (worksheet_id, title) 목록으로 반환한다."""
        return retry(
            lambda: [(ws.id, ws.title) for ws in self._get_spreadsheet().worksheets()]
        )

    def get_url(self, worksheet_id: int) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit#gid={str(worksheet_id)}"

    @staticmethod
    def _convert_list_to_sheet_range(size: int) -> str:
        return f'A:{chr(ord("A") + max(size, 1) - 1)}'

    @staticmethod
    def _yyyymmddhhmmss(timezone: str = "Asia/Seoul") -> str:
        return datetime.now(gettz(timezone)).strftime("%Y%m%d %H%M%S")  # korean time

    def _get_spreadsheet(self) -> Spreadsheet:
        return retry(lambda: self.gs_client.open_by_key(self.spreadsheet_id))

    def _get_worksheet(self, worksheet_id: int) -> Worksheet:
        return retry(
            lambda: self._get_spreadsheet().get_worksheet_by_id(worksheet_id),
            non_retryable=(WorksheetNotFound,),
        )

    def create_bigchat_sheet(self, title: str) -> int:
        # csv 로 뽑을 때 헤더가 없는 편이 낫다고 해서 헤더 행은 비워 둔다
        return retry(lambda: self._create_worksheet(title=title, header_values=[]))

    def delete_row(self, worksheet_id: int, query: str) -> bool:
        """query와 일치하는 첫 셀의 행을 삭제한다. 일치하는 셀이 없으면 아무것도 하지 않는다."""

        def _delete():
            worksheet = self._get_worksheet(worksheet_id)
            cell = worksheet.find(query)
            if cell:
                worksheet.delete_rows(cell.row)

        try:
            retry(_delete, non_retryable=(WorksheetNotFound,))
        except WorksheetNotFound:
            return False
        return True
