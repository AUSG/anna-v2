from urllib.parse import quote

from gspread import Spreadsheet, Worksheet, service_account_from_dict
from gspread.exceptions import WorksheetNotFound

from config.env_config import envs
from shared.utils import with_retry


class GoogleSpreadsheetClient:
    def __init__(self, settings=envs):
        self.gs_client = self._build_gs_client(settings)
        self.gs_client.set_timeout((5, 20))
        self.spreadsheet_id = settings.FORM_SPREADSHEET_ID
        self.members_worksheet_id = settings.MEMBERS_INFO_WORKSHEET_ID

    @staticmethod
    def _build_gs_client(settings=envs):
        return service_account_from_dict(
            {
                "type": settings.GCP_type,
                "project_id": settings.GCP_project_id,
                "private_key_id": settings.GCP_private_key_id,
                "private_key": settings.GCP_private_key.replace("\\n", "\n"),
                "client_email": settings.GCP_client_email,
                "client_id": settings.GCP_client_id,
                "auth_uri": settings.GCP_auth_uri,
                "token_uri": settings.GCP_token_uri,
                "auth_provider_x509_cert_url": settings.GCP_auth_provider_x509_cert_url,
                "client_x509_cert_url": settings.GCP_client_x509_cert_url,
            }
        )

    def sheets_request(self, method, suffix, body=None):
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{quote(self.spreadsheet_id, safe='')}{suffix}"
        return self.gs_client.http_client.request(method, url, json=body).json()

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def get_values(self, worksheet_id: int, cell_range=None) -> list[list[str]]:
        worksheet = self._get_worksheet(worksheet_id)
        return worksheet.get_values(cell_range)

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def get_worksheet_title(self, worksheet_id: int) -> str:
        return self._get_worksheet(worksheet_id).title

    @with_retry()
    def list_worksheets(self) -> list[tuple[int, str]]:
        """스프레드시트의 모든 워크시트를 (worksheet_id, title) 목록으로 반환한다."""
        return [(ws.id, ws.title) for ws in self._get_spreadsheet().worksheets()]

    def get_url(self, worksheet_id: int) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}/edit#gid={worksheet_id!s}"

    @with_retry()
    def _get_spreadsheet(self) -> Spreadsheet:
        return self.gs_client.open_by_key(self.spreadsheet_id)

    @with_retry(non_retryable_exceptions=(WorksheetNotFound,))
    def _get_worksheet(self, worksheet_id: int) -> Worksheet:
        spreadsheet = self._get_spreadsheet()
        return spreadsheet.get_worksheet_by_id(worksheet_id)
