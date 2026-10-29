"""Durable event bindings and participant identities in Sheets developer metadata.

Values stay in A:D for exports. Row metadata follows inserted/moved rows; cancellation
clears only the participant's four cells, never a previously observed row number.
"""

import threading
import time

from gspread.exceptions import APIError
from requests.exceptions import RequestException

from features.bigchat.models import BigchatSheet
from integrations.bigchat_schema import (
    EVENT_KEY,
    PARTICIPANT_KEY,
    SHEET_KEY,
    MetadataIdentity,
    create_participant_requests,
    create_sheet_requests,
    read_values_request,
    write_values_request,
)

_WRITES = threading.RLock()


class BigchatIntegrityError(RuntimeError):
    pass


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

    def _read(self, method, suffix, body=None):
        """Make at most three read attempts; writes require result reconciliation."""
        for delay in (1, 2):
            try:
                return self._client.sheets_request(method, suffix, body)
            except (APIError, RequestException) as error:
                if not _transient(error):
                    raise
                time.sleep(delay)
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
    def event_identity(channel: str, thread_ts: str) -> MetadataIdentity:
        return MetadataIdentity.from_parts(EVENT_KEY, channel, thread_ts)

    def find(self, channel, thread_ts) -> int | None:
        metadata = self._metadata(self.event_identity(channel, thread_ts))
        return None if metadata is None else self._sheet_id(metadata)

    def _bound_event(self, worksheet_id, channel, thread_ts) -> MetadataIdentity:
        event = self.event_identity(channel, thread_ts)
        metadata = self._metadata(event)
        if metadata is None or self._sheet_id(metadata) != worksheet_id:
            raise BigchatIntegrityError("Worksheet is not bound to this Slack thread")
        return event

    def _create_once(self, requests, identity: MetadataIdentity):
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
                worksheet_id = MetadataIdentity.from_parts(
                    SHEET_KEY, channel, thread_ts
                ).metadata_id
                if worksheet_id == self._client.members_worksheet_id:
                    raise BigchatIntegrityError(
                        "Worksheet identity conflicts with member directory"
                    )
                self._create_once(
                    create_sheet_requests(worksheet_id, title, identity), identity
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
                or not isinstance(start, int)
                or end != start + 1
            ):
                raise BigchatIntegrityError(
                    "Participant metadata is not on the bound worksheet row"
                )
        return metadata

    def _values(self, identity: MetadataIdentity, worksheet_id):
        response = self._read(
            "post",
            "/values:batchGetByDataFilter",
            read_values_request(identity, worksheet_id),
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

    def _write_values(self, identity: MetadataIdentity, worksheet_id, values):
        # No row index is sent. Sheets resolves the metadata at write time, even
        # if another participant or a sheet editor inserted/moved a row meanwhile.
        body = write_values_request(identity, worksheet_id, values)
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
            self._create_once(
                create_participant_requests(worksheet_id, identity, values), identity
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
