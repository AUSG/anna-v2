import re
from datetime import datetime
from typing import List, Union, Optional

from cachetools.func import ttl_cache
from dateutil.tz import gettz
from gspread import service_account_from_dict, Worksheet, Spreadsheet
from gspread_formatting import set_column_width
from wrapt import synchronized

from config.env_config import envs
from config.log_config import get_logger

logger = get_logger(__name__)

GCP_type = envs.GCP_type
GCP_project_id = envs.GCP_project_id
GCP_private_key_id = envs.GCP_private_key_id
GCP_private_key = envs.GCP_private_key.replace("\\n", "\n")
GCP_client_email = envs.GCP_client_email
GCP_client_id = envs.GCP_client_id
GCP_auth_uri = envs.GCP_auth_uri
GCP_token_uri = envs.GCP_token_uri
GCP_auth_provider_x509_cert_url = envs.GCP_auth_provider_x509_cert_url
GCP_client_x509_cert_url = envs.GCP_client_x509_cert_url
ANNA_ID = envs.ANNA_ID


class GoogleSpreadsheetClient:
    def __init__(self):
        self.gs_client = self._build_gs_client()

    @staticmethod
    def _build_gs_client():
        return service_account_from_dict(
            {
                "type": GCP_type,
                "project_id": GCP_project_id,
                "private_key_id": GCP_private_key_id,
                "private_key": GCP_private_key,
                "client_email": GCP_client_email,
                "client_id": GCP_client_id,
                "auth_uri": GCP_auth_uri,
                "token_uri": GCP_token_uri,
                "auth_provider_x509_cert_url": GCP_auth_provider_x509_cert_url,
                "client_x509_cert_url": GCP_client_x509_cert_url,
            }
        )

    def create_worksheet(
        self,
        spreadsheet_id: str,
        title_prefix: str,
        header_values: List[str] = None,
        row_size: int = 100,
        col_size: int = 30,
        col_width: int = 220,
    ) -> int:
        if header_values is None:
            header_values = []
        spreadsheet = self._get_spreadsheet(spreadsheet_id)

        worksheet = spreadsheet.add_worksheet(
            f"{title_prefix} {self._yyyymmddhhmmss()}", rows=row_size, cols=col_size
        )
        worksheet.append_row(header_values)
        set_column_width(
            worksheet, self._convert_list_to_sheet_range(len(header_values)), col_width
        )

        return worksheet.id

    def append_row(
        self,
        spreadsheet_id: str,
        worksheet_id: int,
        values: List[str],
        timestamp_on_first_row: bool = True,
    ):
        _values = list(values)
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_id)

        if timestamp_on_first_row:
            _values.insert(0, self._yyyymmddhhmmss())

        worksheet.append_row(_values)

    def get_values(
        self, spreadsheet_id: str, worksheet_id: int, cell_range: str = "A1:A1"
    ) -> List[List[str]]:
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_id)
        return worksheet.get_values(cell_range)

    @staticmethod
    def get_url(spreadsheet_id: str, worksheet_id: int) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={str(worksheet_id)}"

    @staticmethod
    def _convert_list_to_sheet_range(size: int) -> str:
        return f'A:{chr(ord("A") + max(size, 1) - 1)}'

    @staticmethod
    def _yyyymmddhhmmss(timezone: str = "Asia/Seoul") -> str:
        return datetime.now(gettz(timezone)).strftime("%Y%m%d %H%M%S")  # korean time

    @staticmethod
    def _yyyymmdd(timezone: str = "Asia/Seoul") -> str:
        return datetime.now(gettz(timezone)).strftime("%Y%m%d")  # korean time

    def _get_spreadsheet(self, spreadsheet_id: str) -> Spreadsheet:
        return self.gs_client.open_by_key(spreadsheet_id)

    def _get_worksheet(self, spreadsheet_id: str, worksheet_id: int) -> Worksheet:
        spreadsheet = self._get_spreadsheet(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
        return worksheet

    @synchronized
    @ttl_cache(
        maxsize=30, ttl=600
    )  # not thread-safe, 'maxsize' means 'cache call limit'
    def find_or_create_worksheet(
        self,
        slack_client,
        ts: str,
        channel: str,
        spreadsheet_id: str,
        callback_for_new_worksheet,
    ):
        try:
            worksheet_id: Optional[int] = self.find_worksheet_id_in_thread(
                slack_client, ts, channel
            )

            if worksheet_id:
                return worksheet_id

            worksheet_id = self.create_worksheet_in_spread_sheet(spreadsheet_id)

            callback_for_new_worksheet(worksheet_id)
            return worksheet_id

        except Exception as ex:
            logger.error(ex)
            raise ex

    def create_worksheet_in_spread_sheet(self, spreadsheet_id: str) -> Optional[int]:
        worksheet_id: Optional[int] = self.create_worksheet(
            spreadsheet_id=spreadsheet_id,
            title_prefix="[빅챗]",
            header_values=["타임스탬프", "이메일 주소", "이름", "영문 이름", "휴대폰 번호", "학교명 혹은 회사명"],
        )

        return worksheet_id

    @staticmethod
    def find_worksheet_id_in_thread(
        slack_client, ts: str, channel: str
    ) -> Union[int, None]:
        spreadsheet_url_pattern = (
            r"https:\/\/docs.google.com\/spreadsheets\/d\/.*\/edit#gid=(\d*)"
        )

        messages = slack_client.get_replies(ts, channel)

        for message in messages:
            if message.user == ANNA_ID:
                pat = re.search(spreadsheet_url_pattern, message.text)
                if pat is not None and len(pat.groups()) > 0:
                    return int(pat.groups()[0])
        return None
