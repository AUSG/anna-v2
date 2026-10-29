"""Durable event bindings and participant identities in Sheets developer metadata.

Values stay in A:D for exports. Row metadata follows inserted/moved rows; cancellation
clears only the participant's four cells, never a previously observed row number.
"""

import hashlib
import json
import threading
import time

from gspread.exceptions import APIError
from requests.exceptions import RequestException

from features.bigchat.models import BigchatSheet

EVENT_KEY = "anna.bigchat.v1"
PARTICIPANT_KEY = "anna.participant.v1"
_WRITES = threading.RLock()


class BigchatIntegrityError(RuntimeError):
    pass


def _identity(kind, *parts):
    if any(not isinstance(part, str) or not part for part in parts):
        raise ValueError("Bigchat identity fields must be nonempty strings")
    value = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(f"{kind}:{value}".encode()).digest()
    # IDs are spreadsheet-scoped positive int32s. Compare the complete value on
    # every lookup: a hash collision must fail closed, never select another user.
    metadata_id = int.from_bytes(digest[:4], "big") & 0x7FFFFFFF or 1
    return {"metadataId": metadata_id, "metadataKey": kind, "metadataValue": value}


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


class BigchatStore:
    def __init__(self, client):
        self._client = client

    def _metadata(self, identity):
        try:
            metadata = self._client.sheets_request(
                "get", f"/developerMetadata/{identity['metadataId']}"
            )
        except APIError as error:
            if _status(error) == 404:
                return None
            raise
        if metadata.get("visibility") != "DOCUMENT" or any(
            metadata.get(key) != value for key, value in identity.items()
        ):
            raise BigchatIntegrityError(
                "Metadata identity conflict; refusing to use this record"
            )
        return metadata

    def _sheet_id(self, metadata):
        sheet_id = metadata.get("location", {}).get("sheetId")
        if (
            not isinstance(sheet_id, int)
            or sheet_id < 0
            or sheet_id == self._client.members_worksheet_id
        ):
            raise BigchatIntegrityError("Invalid or protected bigchat worksheet")
        return sheet_id

    @staticmethod
    def event_identity(channel, thread_ts):
        return _identity(EVENT_KEY, channel, thread_ts)

    def find(self, channel, thread_ts) -> int | None:
        metadata = self._metadata(self.event_identity(channel, thread_ts))
        return None if metadata is None else self._sheet_id(metadata)

    def _bound_event(self, worksheet_id, channel, thread_ts):
        event = self.event_identity(channel, thread_ts)
        metadata = self._metadata(event)
        if metadata is None or self._sheet_id(metadata) != worksheet_id:
            raise BigchatIntegrityError("Worksheet is not bound to this Slack thread")
        return event

    def _create_once(self, requests, identity):
        """The unique metadata ID guards the entire atomic batch against replay."""
        for attempt in range(3):
            try:
                self._client.sheets_request(
                    "post", ":batchUpdate", {"requests": requests}
                )
                return
            except (APIError, RequestException) as error:
                # A lost response or another creator may have committed the same
                # batch. Never replay an unguarded append/insert operation.
                if self._metadata(identity) is not None:
                    return
                if not _transient(error) or attempt == 2:
                    raise
                time.sleep(2**attempt)

    @staticmethod
    def _create_metadata(identity, location):
        return {
            "createDeveloperMetadata": {
                "developerMetadata": {
                    **identity,
                    "visibility": "DOCUMENT",
                    "location": location,
                }
            }
        }

    def get_sheet(self, worksheet_id: int) -> BigchatSheet:
        return BigchatSheet(
            worksheet_id=worksheet_id,
            sheet_name=self._client.get_worksheet_title(worksheet_id),
            sheet_url=self._client.get_url(worksheet_id),
        )

    def create(self, title: str, *, channel: str, thread_ts: str) -> BigchatSheet:
        with _WRITES:
            identity = self.event_identity(channel, thread_ts)
            existing = self._metadata(identity)
            if existing is None:
                worksheet_id = _identity("anna.sheet.v1", channel, thread_ts)[
                    "metadataId"
                ]
                if worksheet_id == self._client.members_worksheet_id:
                    raise BigchatIntegrityError(
                        "Worksheet identity conflicts with member directory"
                    )
                self._create_once(
                    [
                        {
                            "addSheet": {
                                "properties": {
                                    "sheetId": worksheet_id,
                                    "title": title,
                                    "gridProperties": {
                                        "rowCount": 100,
                                        "columnCount": 4,
                                    },
                                }
                            }
                        },
                        self._create_metadata(identity, {"sheetId": worksheet_id}),
                        {
                            "updateDimensionProperties": {
                                "range": {
                                    "sheetId": worksheet_id,
                                    "dimension": "COLUMNS",
                                    "startIndex": 0,
                                    "endIndex": 4,
                                },
                                "properties": {"pixelSize": 220},
                                "fields": "pixelSize",
                            }
                        },
                    ],
                    identity,
                )
                self._bound_event(worksheet_id, channel, thread_ts)
            else:
                worksheet_id = self._sheet_id(existing)
            created = self.get_sheet(worksheet_id)
            if created.sheet_name != title:
                raise BigchatIntegrityError(
                    "This Slack thread already has a different bigchat"
                )
            return created

    @staticmethod
    def _participant(event, user_id):
        return _identity(PARTICIPANT_KEY, str(event["metadataId"]), user_id)

    def _participant_metadata(self, identity, worksheet_id):
        metadata = self._metadata(identity)
        if metadata is not None:
            location = metadata.get("location", {}).get("dimensionRange", {})
            start, end = location.get("startIndex"), location.get("endIndex")
            if (
                location.get("sheetId") != worksheet_id
                or location.get("dimension") != "ROWS"
                or not isinstance(start, int)
                or end != start + 1
            ):
                raise BigchatIntegrityError(
                    "Participant metadata is not on the bound worksheet row"
                )
        return metadata

    @staticmethod
    def _filter(identity, worksheet_id):
        return {
            "developerMetadataLookup": {
                **identity,
                "visibility": "DOCUMENT",
                "locationType": "ROW",
                "metadataLocation": {"sheetId": worksheet_id},
                "locationMatchingStrategy": "INTERSECTING_LOCATION",
            }
        }

    def _values(self, identity, worksheet_id):
        response = self._client.sheets_request(
            "post",
            "/values:batchGetByDataFilter",
            {
                "dataFilters": [self._filter(identity, worksheet_id)],
                "valueRenderOption": "UNFORMATTED_VALUE",
            },
        )
        ranges = response.get("valueRanges", [])
        if len(ranges) != 1:
            raise BigchatIntegrityError("Participant row disappeared or is ambiguous")
        rows = ranges[0]["valueRange"].get("values", [])
        if len(rows) > 1:
            raise BigchatIntegrityError(
                "Participant metadata selected more than one row"
            )
        row = rows[0] if rows else []
        return (row + [""] * 4)[:4]

    def _write_values(self, identity, worksheet_id, values):
        # No row index is sent. Sheets resolves the metadata at write time, even
        # if another participant or a sheet editor inserted/moved a row meanwhile.
        body = {
            "valueInputOption": "RAW",
            "data": [
                {
                    "dataFilter": self._filter(identity, worksheet_id),
                    "majorDimension": "ROWS",
                    "values": [values],
                }
            ],
        }
        for attempt in range(3):
            try:
                response = self._client.sheets_request(
                    "post", "/values:batchUpdateByDataFilter", body
                )
                if response.get("totalUpdatedRows") != 1:
                    raise BigchatIntegrityError("Participant row was not updated")
                return
            except (APIError, RequestException) as error:
                if self._values(identity, worksheet_id) == values:
                    return
                if not _transient(error) or attempt == 2:
                    raise
                time.sleep(2**attempt)

    def register(self, worksheet_id, user_id, values, *, channel, thread_ts) -> bool:
        if len(values) != 4 or any(not isinstance(value, str) for value in values):
            raise ValueError("Registration must contain four text values")
        with _WRITES:
            event = self._bound_event(worksheet_id, channel, thread_ts)
            identity = self._participant(event, user_id)
            if self._participant_metadata(identity, worksheet_id) is not None:
                previous = self._values(identity, worksheet_id)
                if previous != values:
                    self._write_values(identity, worksheet_id, values)
                return not any(previous)
            row_range = {
                "sheetId": worksheet_id,
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": 1,
            }
            self._create_once(
                [
                    {
                        "insertDimension": {
                            "range": row_range,
                            "inheritFromBefore": False,
                        }
                    },
                    {
                        "updateCells": {
                            "start": {
                                "sheetId": worksheet_id,
                                "rowIndex": 0,
                                "columnIndex": 0,
                            },
                            "rows": [
                                {
                                    "values": [
                                        {"userEnteredValue": {"stringValue": value}}
                                        for value in values
                                    ]
                                }
                            ],
                            "fields": "userEnteredValue",
                        }
                    },
                    self._create_metadata(
                        identity,
                        {"dimensionRange": row_range},
                    ),
                ],
                identity,
            )
            self._participant_metadata(identity, worksheet_id)
            return True

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
