"""Storage boundary shared by every Bigchat creation and registration path."""

from collections.abc import Iterable

from features.bigchat.models import BigchatCreated
from features.bigchat.services.sheet_link import extract_worksheet_id
from integrations.google_sheets import GoogleSpreadsheetClient


class BigchatStore:
    def __init__(self, client: GoogleSpreadsheetClient):
        self._client = client

    def create(self, title: str) -> BigchatCreated:
        worksheet_id = self._client.create_bigchat_sheet(title)
        return BigchatCreated(
            worksheet_id=worksheet_id,
            sheet_name=title,
            sheet_url=self._client.get_url(worksheet_id),
        )

    def find(self, texts: Iterable[str]) -> int | None:
        return extract_worksheet_id(texts)

    def get_worksheet_title(self, worksheet_id: int) -> str:
        return self._client.get_worksheet_title(worksheet_id)

    def register(self, worksheet_id: int, values: list[str]) -> bool:
        return self._client.append_row_if_absent(worksheet_id, values)

    def cancel(self, worksheet_id: int, email: str):
        return self._client.delete_row(worksheet_id, email)
