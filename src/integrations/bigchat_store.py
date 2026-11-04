"""Event and participant identities with atomic, replay-guarded Sheets writes.

One process/worker serializes its own writes. Native row operations follow row
metadata; replacing cell values without moving metadata is unsupported.
"""

import threading
import time
from functools import wraps
from uuid import uuid4

from gspread.exceptions import APIError
from requests.exceptions import RequestException

from features.bigchat.errors import (
    BigchatAlreadyCreated,
    BigchatIntegrityError,
    BigchatNameConflict,
    BigchatSheetMissing,
    BigchatStorageError,
)
from features.bigchat.models import BigchatSheet
from integrations.bigchat_schema import (
    EVENT_KEY,
    PARTICIPANT_KEY,
    REGISTRATION_KEY,
    SHEET_KEY,
    MetadataIdentity,
    create_participant_requests,
    create_sheet_requests,
    read_values_request,
    write_values_request,
)

_WRITES = threading.RLock()


def _status(error):
    return getattr(getattr(error, "response", None), "status_code", None)


def _transient(error):
    return isinstance(error, RequestException) or _status(error) in (
        408,
        429,
        500,
        502,
        503,
        504,
    )


def _storage_errors(method):
    @wraps(method)
    def invoke(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (APIError, RequestException) as error:
            raise BigchatStorageError(
                "Sheets operation could not be confirmed"
            ) from error

    return invoke


def _location(metadata):
    return {
        k: v for k, v in metadata.get("location", {}).items() if k != "locationType"
    }


class BigchatStore:
    def __init__(self, client):
        self._client = client

    def _read(self, method, suffix, body=None):
        return self._client.sheets_request(method, suffix, body)

    def _metadata(self, identity: MetadataIdentity):
        try:
            metadata = self._read("get", f"/developerMetadata/{identity.metadata_id}")
        except APIError as error:
            if _status(error) == 404:
                return None
            raise
        if metadata.get("visibility") != "DOCUMENT" or any(
            metadata.get(key) != value for key, value in identity.to_api().items()
        ):
            raise BigchatIntegrityError("Metadata identity conflict")
        return metadata

    def _sheets(self):
        response = self._read("get", "?fields=sheets.properties")
        return [sheet["properties"] for sheet in response.get("sheets", [])]

    def _worksheet_properties(self, worksheet_id):
        if (
            type(worksheet_id) is not int
            or worksheet_id < 0
            or worksheet_id == self._client.members_worksheet_id
        ):
            raise BigchatIntegrityError("Invalid or protected bigchat worksheet")
        sheet = next((s for s in self._sheets() if s["sheetId"] == worksheet_id), None)
        if sheet is None:
            raise BigchatSheetMissing("The bound worksheet has been deleted")
        return sheet

    @staticmethod
    def event_identity(channel: str, thread_ts: str) -> MetadataIdentity:
        return MetadataIdentity.from_parts(EVENT_KEY, channel, thread_ts)

    @staticmethod
    def sheet_identity(channel: str, thread_ts: str) -> MetadataIdentity:
        return MetadataIdentity.from_parts(SHEET_KEY, channel, thread_ts)

    def _resolve(self, channel, thread_ts):
        event = self.event_identity(channel, thread_ts)
        record = self._metadata(event)
        if record is None:
            return None
        if _location(record) != {"spreadsheet": True}:
            raise BigchatIntegrityError("Event record is not on the spreadsheet")
        sheet = self.sheet_identity(channel, thread_ts)
        worksheet_id = sheet.metadata_id
        if worksheet_id == self._client.members_worksheet_id:
            raise BigchatIntegrityError("Protected bigchat worksheet")
        binding = self._metadata(sheet)
        if binding is None:
            # Distinguish deleted tabs from removed/corrupted binding metadata.
            self._worksheet_properties(worksheet_id)
            raise BigchatIntegrityError("The worksheet binding is missing")
        if _location(binding) != {"sheetId": worksheet_id}:
            raise BigchatIntegrityError("The worksheet binding has moved")
        return event, worksheet_id

    @_storage_errors
    def find(self, channel, thread_ts) -> int | None:
        result = self._resolve(channel, thread_ts)
        return None if result is None else result[1]

    def _bound_event(self, worksheet_id, channel, thread_ts) -> MetadataIdentity:
        result = self._resolve(channel, thread_ts)
        if result is None or result[1] != worksheet_id:
            raise BigchatIntegrityError("Worksheet is not bound to this Slack thread")
        return result[0]

    def _create_once(self, requests, identity: MetadataIdentity):
        """A unique metadata ID guards the entire atomic batch against replay."""
        for attempt in range(3):
            try:
                self._client.sheets_request(
                    "post", ":batchUpdate", {"requests": requests}
                )
                return
            except (APIError, RequestException) as error:
                if self._metadata(identity) is not None:
                    return
                if not _transient(error) or attempt == 2:
                    raise
                time.sleep(2**attempt)

    @_storage_errors
    def get_sheet(self, worksheet_id: int) -> BigchatSheet:
        return BigchatSheet(
            worksheet_id=worksheet_id,
            sheet_name=self._worksheet_properties(worksheet_id)["title"],
            sheet_url=self._client.get_url(worksheet_id),
        )

    @_storage_errors
    def create(self, title: str, *, channel: str, thread_ts: str) -> BigchatSheet:
        with _WRITES:
            result = self._resolve(channel, thread_ts)
            if result is None:
                event = self.event_identity(channel, thread_ts)
                sheet = self.sheet_identity(channel, thread_ts)
                worksheet_id = sheet.metadata_id
                if worksheet_id == self._client.members_worksheet_id:
                    raise BigchatIntegrityError(
                        "Worksheet identity conflicts with member directory"
                    )
                sheets = self._sheets()
                if any(s["title"] == title for s in sheets):
                    raise BigchatNameConflict(
                        "A different worksheet already has this title"
                    )
                requests = create_sheet_requests(
                    title, event, sheet, min(3, len(sheets))
                )
                try:
                    self._create_once(requests, event)
                except APIError as error:
                    # Another creator may have used the name after the preflight.
                    if _status(error) == 400 and any(
                        s["title"] == title for s in self._sheets()
                    ):
                        raise BigchatNameConflict(
                            "The title was taken during creation"
                        ) from error
                    raise
                self._bound_event(worksheet_id, channel, thread_ts)
            else:
                worksheet_id = result[1]
            created = self.get_sheet(worksheet_id)
            if created.sheet_name != title:
                raise BigchatAlreadyCreated(
                    "This Slack thread already has a different bigchat"
                )
            return created

    @staticmethod
    def _participant(event: MetadataIdentity, user_id: str) -> MetadataIdentity:
        return MetadataIdentity.from_parts(
            PARTICIPANT_KEY, str(event.metadata_id), user_id
        )

    def _participant_metadata(self, identity: MetadataIdentity, worksheet_id):
        metadata = self._metadata(identity)
        if metadata is not None:
            location = metadata.get("location", {}).get("dimensionRange", {})
            start, end = location.get("startIndex"), location.get("endIndex")
            if (
                location.get("sheetId") != worksheet_id
                or location.get("dimension") != "ROWS"
                or type(start) is not int
                or start < 0
                or end != start + 1
            ):
                raise BigchatIntegrityError(
                    "Participant metadata is not on the bound worksheet row"
                )
        return metadata

    def _values(self, identity: MetadataIdentity, worksheet_id):
        response = self._read_on_sheet(
            worksheet_id,
            "post",
            "/values:batchGetByDataFilter",
            read_values_request(identity, worksheet_id),
        )
        ranges = response.get("valueRanges", [])
        if len(ranges) != 1:
            self._worksheet_properties(worksheet_id)
            raise BigchatIntegrityError("Participant row disappeared or is ambiguous")
        rows = ranges[0]["valueRange"].get("values", [])
        if len(rows) > 1:
            raise BigchatIntegrityError(
                "Participant metadata selected more than one row"
            )
        row = rows[0] if rows else []
        return (row + [""] * 4)[:4]

    def _read_on_sheet(self, worksheet_id, method, suffix, body):
        try:
            return self._read(method, suffix, body)
        except APIError as error:
            if _status(error) in (400, 404):
                self._worksheet_properties(worksheet_id)
            raise

    def _write_values(self, identity: MetadataIdentity, worksheet_id, values):
        body = write_values_request(identity, worksheet_id, values)
        for attempt in range(3):
            try:
                response = self._client.sheets_request(
                    "post", "/values:batchUpdateByDataFilter", body
                )
                if response.get("totalUpdatedRows") != 1:
                    self._worksheet_properties(worksheet_id)
                    raise BigchatIntegrityError("Participant row was not updated")
                return
            except (APIError, RequestException) as error:
                if self._values(identity, worksheet_id) == values:
                    return
                if not _transient(error) or attempt == 2:
                    raise
                time.sleep(2**attempt)

    def _append(self, worksheet_id, identity, values, *, rejoining):
        props = self._worksheet_properties(worksheet_id)
        # A grid filter binds this read to sheetId even if its title is renamed.
        response = self._read_on_sheet(
            worksheet_id,
            "post",
            "/values:batchGetByDataFilter",
            {
                "dataFilters": [{"gridRange": {"sheetId": worksheet_id}}],
                "valueRenderOption": "UNFORMATTED_VALUE",
            },
        )
        ranges = response.get("valueRanges", [])
        if len(ranges) != 1:
            self._worksheet_properties(worksheet_id)
            raise BigchatIntegrityError("Could not locate the insertion position")
        row_index = len(ranges[0]["valueRange"].get("values", []))
        grid_rows = props["gridProperties"]["rowCount"]
        if row_index > grid_rows:
            raise BigchatIntegrityError(
                "Worksheet changed while selecting insertion position"
            )
        registration = (
            MetadataIdentity.from_parts(
                REGISTRATION_KEY, str(identity.metadata_id), uuid4().hex
            )
            if rejoining
            else None
        )
        requests = create_participant_requests(
            worksheet_id, identity, values, row_index, grid_rows, registration
        )
        try:
            self._create_once(requests, registration or identity)
        except APIError as error:
            if _status(error) in (400, 404):
                self._worksheet_properties(worksheet_id)
            raise
        if self._participant_metadata(identity, worksheet_id) is None:
            raise BigchatIntegrityError("Registration metadata disappeared")

    @_storage_errors
    def register(self, worksheet_id, user_id, values, *, channel, thread_ts) -> bool:
        if len(values) != 4 or any(not isinstance(value, str) for value in values):
            raise ValueError("Registration must contain four text values")
        with _WRITES:
            event = self._bound_event(worksheet_id, channel, thread_ts)
            identity = self._participant(event, user_id)
            existing = self._participant_metadata(identity, worksheet_id)
            if existing is not None:
                previous = self._values(identity, worksheet_id)
                if any(previous):
                    if previous != values:
                        self._write_values(identity, worksheet_id, values)
                    return False
            self._append(worksheet_id, identity, values, rejoining=existing is not None)
            return True

    @_storage_errors
    def cancel(self, worksheet_id, user_id, *, channel, thread_ts) -> bool:
        with _WRITES:
            event = self._bound_event(worksheet_id, channel, thread_ts)
            identity = self._participant(event, user_id)
            if self._participant_metadata(identity, worksheet_id) is None:
                return False
            previous = self._values(identity, worksheet_id)
            if any(previous):
                self._write_values(identity, worksheet_id, ["", "", "", ""])
            return bool(any(previous))
