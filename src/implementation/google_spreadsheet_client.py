import logging
from datetime import datetime
from typing import List, Optional

from dateutil.tz import gettz
from gspread import service_account_from_dict, Worksheet, Spreadsheet
from gspread_formatting import set_column_width

from config.env_config import envs
from util.utils import with_retry


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

    @with_retry()
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

    @with_retry()
    def get_values(self, worksheet_id: int, cell_range=None) -> List[List[str]]:
        worksheet = self._get_worksheet(worksheet_id)
        return worksheet.get_values(cell_range)

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

    @with_retry()
    def _get_worksheet(self, worksheet_id: int) -> Worksheet:
        spreadsheet = self._get_spreadsheet()
        worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
        return worksheet

    @with_retry()
    def create_bigchat_sheet(self, title=None) -> Optional[int]:
        worksheet_id: Optional[int] = self._create_worksheet(
            title=title,
            header_values=[
                # csv 만들때 헤더 없는게 낫다고 해서 전부 주석처리 함
                # "FirstName",
                # "LastName",
                # "FullName",
                # "Email",
                # "SchoolOrCompany",
                # "Phone",
            ],
        )

        return worksheet_id

    @with_retry()
    def delete_row(self, worksheet_id: int, query: str):
        """
        XXX: 실제로 삭제할 정보가 없어서 아무 동작을 하지 않아도 에러를 뱉지 않는다.

        :param worksheet_id:
        :param query: str, re.RegexObject (e.g, re.compile(".*"))
        :return:
        """
        worksheet = self._get_worksheet(worksheet_id)

        cell = worksheet.find(query)
        if cell:
            worksheet.delete_rows(cell.row)
