import logging
import threading
from datetime import datetime
from typing import List, Optional, Tuple

from dateutil.tz import gettz
from gspread import service_account_from_dict, Worksheet, Spreadsheet
from gspread.exceptions import WorksheetNotFound
from gspread_formatting import set_column_width

from config.env_config import envs
from shared.retry import with_retry

# append_row_if_absent 의 확인-후-추가를 원자적으로 만드는 프로세스 전역 락.
# 이 앱은 단일 프로세스(gunicorn --workers 1)로 떠 있어서 프로세스 락으로 충분하다.
_APPEND_IF_ABSENT_LOCK = threading.Lock()


class GoogleSpreadsheetClient:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.gs_client = self._build_gs_client()
        self.spreadsheet_id = envs.FORM_SPREADSHEET_ID

    @staticmethod
    def _build_gs_client():
        return service_account_from_dict(
            {
                "type": envs.GCP_type,
                "project_id": envs.GCP_project_id,
                "private_key_id": envs.GCP_private_key_id,
                "private_key": envs.GCP_private_key.replace("\\n", "\n"),
                "client_email": envs.GCP_client_email,
                "client_id": envs.GCP_client_id,
                "auth_uri": envs.GCP_auth_uri,
                "token_uri": envs.GCP_token_uri,
                "auth_provider_x509_cert_url": envs.GCP_auth_provider_x509_cert_url,
                "client_x509_cert_url": envs.GCP_client_x509_cert_url,
            }
        )

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

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def append_row(
        self,
        worksheet_id: int,
        values: List[str],
        timestamp_on_first_row: bool = False,
    ):
        _values = list(values)
        worksheet = self._get_worksheet(worksheet_id)

        if timestamp_on_first_row:
            _values.insert(0, self._yyyymmddhhmmss())

        worksheet.append_row(_values)

    def append_row_if_absent(self, worksheet_id: int, values: List[str]) -> bool:
        """같은 행이 이미 있으면 추가하지 않는다. 실제로 추가했으면 True.

        동시 요청의 중복 확인과 행 추가를 프로세스 전역 락으로 직렬화한다.
        """
        with _APPEND_IF_ABSENT_LOCK:
            if list(values) in self.get_values(worksheet_id):
                return False
            self.append_row(worksheet_id, values)
            return True

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def get_values(self, worksheet_id: int, cell_range=None) -> List[List[str]]:
        worksheet = self._get_worksheet(worksheet_id)
        return worksheet.get_values(cell_range)

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def get_worksheet_title(self, worksheet_id: int) -> str:
        return self._get_worksheet(worksheet_id).title

    @with_retry()
    def list_worksheets(self) -> List[Tuple[int, str]]:
        """스프레드시트의 모든 워크시트를 (worksheet_id, title) 목록으로 반환한다."""
        return [(ws.id, ws.title) for ws in self._get_spreadsheet().worksheets()]

    def get_url(self, worksheet_id: int) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit#gid={str(worksheet_id)}"

    @staticmethod
    def _convert_list_to_sheet_range(size: int) -> str:
        return f'A:{chr(ord("A") + max(size, 1) - 1)}'

    @staticmethod
    def _yyyymmddhhmmss(timezone: str = "Asia/Seoul") -> str:
        return datetime.now(gettz(timezone)).strftime("%Y%m%d %H%M%S")  # korean time

    @with_retry()
    def _get_spreadsheet(self) -> Spreadsheet:
        return self.gs_client.open_by_key(self.spreadsheet_id)

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def _get_worksheet(self, worksheet_id: int) -> Worksheet:
        spreadsheet = self._get_spreadsheet()
        worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
        return worksheet

    @with_retry()
    def create_bigchat_sheet(self, title=None) -> Optional[int]:
        worksheet_id: Optional[int] = self._create_worksheet(
            title=title,
            header_values=[],
        )

        return worksheet_id

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def delete_row(self, worksheet_id: int, query: str):
        """query와 일치하는 첫 셀의 행을 삭제한다. 일치하는 셀이 없으면 무시한다."""
        worksheet = self._get_worksheet(worksheet_id)

        cell = worksheet.find(query)
        if cell:
            worksheet.delete_rows(cell.row)
