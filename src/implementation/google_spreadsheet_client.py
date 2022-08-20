import logging
import os
from datetime import datetime
from typing import List
from dateutil.tz import gettz
from gspread import service_account_from_dict, Worksheet, Spreadsheet
from gspread_formatting import set_column_width

logger = logging.getLogger(__name__)

GCP_type = os.environ.get('GCP_type')
GCP_project_id = os.environ.get('GCP_project_id')
GCP_private_key_id = os.environ.get('GCP_private_key_id')
GCP_private_key = os.environ.get('GCP_private_key').replace("\\n", "\n")
GCP_client_email = os.environ.get('GCP_client_email')
GCP_client_id = os.environ.get('GCP_client_id')
GCP_auth_uri = os.environ.get('GCP_auth_uri')
GCP_token_uri = os.environ.get('GCP_token_uri')
GCP_auth_provider_x509_cert_url = os.environ.get('GCP_auth_provider_x509_cert_url')
GCP_client_x509_cert_url = os.environ.get('GCP_client_x509_cert_url')

__singleton = None


class GoogleSpreadsheetClient:
    """
    싱글톤으로 사용하고 싶기 때문에, (강제하지는 않지만)
    `google_spreadsheet_client.get_instance()`로 인스턴스를 호출하기를 강력하게 권고함
    """

    def __init__(self):
        self.gs_client = service_account_from_dict({
            'type': GCP_type,
            'project_id': GCP_project_id,
            'private_key_id': GCP_private_key_id,
            'private_key': GCP_private_key,
            'client_email': GCP_client_email,
            'client_id': GCP_client_id,
            'auth_uri': GCP_auth_uri,
            'token_uri': GCP_token_uri,
            'auth_provider_x509_cert_url': GCP_auth_provider_x509_cert_url,
            'client_x509_cert_url': GCP_client_x509_cert_url
        })

    def create_worksheet(self, spreadsheet_id: str, title_prefix: str, header_values: List[str] = None,
                         row_size: int = 100, col_size: int = 30, col_width: int = 220) -> int:
        if header_values is None:
            header_values = []
        spreadsheet = self._get_spreadsheet(spreadsheet_id)

        worksheet = spreadsheet.add_worksheet(f"{title_prefix} {self._get_now()}", rows=row_size, cols=col_size)
        worksheet.append_row(header_values)
        set_column_width(worksheet, self._convert_list_to_sheet_range(len(header_values)), col_width)

        return worksheet.id

    def append_row(self, spreadsheet_id: str, worksheet_id: int, values: List[str],
                   timestamp_on_first_row: bool = True):
        _values = list(values)
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_id)

        if timestamp_on_first_row:
            _values.append(self._get_now())

        worksheet.append_row(_values)

    def get_values(self, spreadsheet_id: str, worksheet_id: int, cell_range: str = 'A1:A1') -> List[List[str]]:
        worksheet = self._get_worksheet(spreadsheet_id, worksheet_id)
        return worksheet.get_values(cell_range)

    @staticmethod
    def get_url(spreadsheet_id: str, worksheet_id: int) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={str(worksheet_id)}"

    @staticmethod
    def _convert_list_to_sheet_range(size: int) -> str:
        if size < 1:
            size = 1
        return f'A:{chr(ord("A") + size - 1)}'

    @staticmethod
    def _get_now(timezone: str = 'Asia/Seoul') -> str:
        return datetime.now(gettz(timezone)).strftime('%Y%m%d %H%M%S')  # korean time

    def _get_spreadsheet(self, spreadsheet_id: str) -> Spreadsheet:
        return self.gs_client.open_by_key(spreadsheet_id)

    def _get_worksheet(self, spreadsheet_id: str, worksheet_id: int) -> Worksheet:
        spreadsheet = self._get_spreadsheet(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet_by_id(worksheet_id)
        return worksheet


def get_instance():
    global __singleton
    if __singleton is None:
        __singleton = GoogleSpreadsheetClient()
    return __singleton
