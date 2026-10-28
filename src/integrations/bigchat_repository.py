from features.bigchat.models import BigchatCreated
from integrations.google_sheets import GoogleSpreadsheetClient


class SpreadsheetBigchatRepository:
    def __init__(self, client: GoogleSpreadsheetClient):
        self._client = client

    def create(
        self, sheet_name: str, *, channel: str, thread_ts: str
    ) -> BigchatCreated:
        worksheet_id = self._client.create_bigchat_sheet(
            sheet_name, channel=channel, thread_ts=thread_ts
        )
        return BigchatCreated(
            worksheet_id=worksheet_id,
            sheet_name=sheet_name,
            sheet_url=self._client.get_url(worksheet_id),
        )
