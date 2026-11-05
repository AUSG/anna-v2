"""Event and participant identities with atomic, replay-guarded Sheets writes.

One process/worker serializes its own writes. Native row operations follow row
metadata; replacing cell values without moving metadata is unsupported.
"""

import json
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
    ReactionSuperseded,
)
from features.bigchat.models import BigchatSheet
from integrations.bigchat_participant import (
    Participant,
    reaction_identity,
    transition_request,
)
from integrations.bigchat_schema import (
    EVENT_KEY,
    PARTICIPANT_KEY,
    REGISTRATION_KEY,
    SHEET_KEY,
    MetadataIdentity,
    create_participant_requests,
    create_participant_state_request,
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
        # Bindings this instance verified, keyed by (channel, thread_ts). Each
        # Slack event gets a new store, so register/cancel after find (and the
        # backfill after create) skip re-reading the same two metadata records.
        self._bindings = {}

    def _read(self, method, suffix, body=None):
        return self._client.sheets_request(method, suffix, body)

    def _raw_metadata(self, metadata_id):
        try:
            return self._read("get", f"/developerMetadata/{metadata_id}")
        except APIError as error:
            if _status(error) == 404:
                return None
            raise

    def _metadata(self, identity: MetadataIdentity):
        metadata = self._raw_metadata(identity.metadata_id)
        if metadata is None:
            return None
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

    def sheet_url(self, channel: str, thread_ts: str) -> str:
        """The link posted for this thread's bigchat, known without reading Sheets."""
        return self._client.get_url(self.sheet_identity(channel, thread_ts).metadata_id)

    def _resolve(self, channel, thread_ts):
        # A fresh lookup replaces whatever this instance verified before.
        self._bindings.pop((channel, thread_ts), None)
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
        self._bindings[(channel, thread_ts)] = (event, worksheet_id)
        return event, worksheet_id

    @_storage_errors
    def find(self, channel, thread_ts) -> int | None:
        result = self._resolve(channel, thread_ts)
        return None if result is None else result[1]

    def _bound_event(self, worksheet_id, channel, thread_ts) -> MetadataIdentity:
        # A tab deleted after the lookup is still reported: its row metadata goes
        # with it, so the participant and sheet reads that follow notice.
        result = self._bindings.get((channel, thread_ts)) or self._resolve(
            channel, thread_ts
        )
        if result is None or result[1] != worksheet_id:
            raise BigchatIntegrityError("Worksheet is not bound to this Slack thread")
        return result[0]

    def _write_and_confirm(self, send, confirmed):
        """Only a successful confirmation read permits another guarded write."""
        for attempt in range(3):
            try:
                send()
                return
            except (APIError, RequestException) as error:
                if confirmed():
                    return
                if not _transient(error) or attempt == 2:
                    raise
                time.sleep(2**attempt)

    def _create_once(self, requests, identity: MetadataIdentity, *, confirmed=None):
        """A unique metadata ID guards the entire atomic batch against replay."""
        self._write_and_confirm(
            lambda: self._client.sheets_request(
                "post", ":batchUpdate", {"requests": requests}
            ),
            confirmed or (lambda: self._metadata(identity) is not None),
        )

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
        metadata = self._raw_metadata(identity.metadata_id)
        return (
            None
            if metadata is None
            else Participant.read(metadata, identity, worksheet_id)
        )

    def _confirm_participant(self, owner, worksheet_id, desired, previous=None):
        current = self._participant_metadata(owner, worksheet_id)
        if current is None:
            self._worksheet_properties(worksheet_id)
            return False
        if current.identity == desired:
            return True
        if previous is not None and current.identity == previous.identity:
            return False
        raise ReactionSuperseded("Participant revision has changed")

    def _prepare_participant(self, owner, worksheet_id, existing, event_ts, active):
        if existing is not None:
            existing.accepts(event_ts, active)
            if event_ts is None or existing.event_ts == event_ts:
                return existing.identity
        desired = reaction_identity(owner, event_ts, active, uuid4().hex)
        if existing is None:
            return desired

        def confirm():
            return self._confirm_participant(owner, worksheet_id, desired, existing)

        def send():
            response = self._client.sheets_request(
                "post",
                ":batchUpdate",
                {
                    "requests": [
                        transition_request(existing.identity, desired, worksheet_id)
                    ]
                },
            )
            replies = response.get("replies", [])
            changed = (
                replies[0]
                .get("updateDeveloperMetadata", {})
                .get("developerMetadata", [])
                if len(replies) == 1
                else []
            )
            if len(changed) == 1:
                updated = Participant.read(changed[0], owner, worksheet_id)
                if updated.identity == desired:
                    return
            if not confirm():
                raise BigchatIntegrityError("Participant revision was not updated")

        self._write_and_confirm(send, confirm)
        return desired

    @_storage_errors
    def active_user_ids(self, worksheet_id: int) -> list[str] | None:
        """Read the same identities and active A:D state used by registration.

        None identifies a legacy tab, whose participants still use email lookup.
        Filters include the exact reaction revision, so a concurrent cancellation
        cannot turn an old snapshot into a reminder recipient.
        """
        if (
            type(worksheet_id) is not int
            or worksheet_id < 0
            or worksheet_id == self._client.members_worksheet_id
        ):
            raise BigchatIntegrityError("Invalid or protected bigchat worksheet")
        binding = self._raw_metadata(worksheet_id)
        if binding is None:
            return None
        if binding.get("metadataKey") != SHEET_KEY:
            raise BigchatIntegrityError("Worksheet identity conflict")
        try:
            channel, thread_ts = json.loads(binding["metadataValue"])
            sheet = self.sheet_identity(channel, thread_ts)
        except (TypeError, ValueError, KeyError) as error:
            raise BigchatIntegrityError("Invalid worksheet binding") from error
        if (
            sheet.metadata_id != worksheet_id
            or binding.get("visibility") != "DOCUMENT"
            or any(binding.get(k) != v for k, v in sheet.to_api().items())
            or _location(binding) != {"sheetId": worksheet_id}
        ):
            raise BigchatIntegrityError("Worksheet identity conflict")
        event = self.event_identity(channel, thread_ts)
        record = self._metadata(event)
        if record is None or _location(record) != {"spreadsheet": True}:
            raise BigchatIntegrityError("Worksheet has no valid event record")
        response = self._read(
            "post",
            "/developerMetadata:search",
            {
                "dataFilters": [
                    {
                        "developerMetadataLookup": {
                            "metadataKey": PARTICIPANT_KEY,
                            "visibility": "DOCUMENT",
                            "metadataLocation": {"sheetId": worksheet_id},
                            "locationMatchingStrategy": "INTERSECTING_LOCATION",
                        }
                    }
                ]
            },
        )
        participants = {}
        for match in response.get("matchedDeveloperMetadata", []):
            metadata = match.get("developerMetadata", {})
            try:
                user = json.loads(metadata["metadataValue"])[1]
                owner = self._participant(event, user)
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise BigchatIntegrityError("Invalid participant owner") from error
            participant = Participant.read(metadata, owner, worksheet_id)
            if participant.row is not None and participant.active is not False:
                participants[owner.metadata_id] = participant
        if not participants:
            return []
        filters = [
            read_values_request(p.identity, worksheet_id)["dataFilters"][0]
            for p in participants.values()
        ]
        response = self._read_on_sheet(
            worksheet_id,
            "post",
            "/values:batchGetByDataFilter",
            {
                "dataFilters": filters,
                "valueRenderOption": "UNFORMATTED_VALUE",
            },
        )
        active, seen = [], set()
        for matched in response.get("valueRanges", []):
            matched_filters = matched.get("dataFilters", [])
            # Map results back by metadata ID only. The API need not echo a filter
            # exactly as sent, while the server already matched each filter on
            # its full revision value before returning this range.
            lookup = (
                matched_filters[0].get("developerMetadataLookup", {})
                if len(matched_filters) == 1
                else {}
            )
            mid = lookup.get("metadataId")
            if mid not in participants:
                raise BigchatIntegrityError("Ambiguous participant read")
            rows = matched.get("valueRange", {}).get("values", [])
            if mid in seen or len(rows) > 1:
                raise BigchatIntegrityError("Ambiguous participant row")
            seen.add(mid)
            if rows and any(rows[0][:4]):
                active.append(participants[mid].user_id)
        return active

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

        def send():
            response = self._client.sheets_request(
                "post", "/values:batchUpdateByDataFilter", body
            )
            if response.get("totalUpdatedRows") != 1:
                self._worksheet_properties(worksheet_id)
                raise BigchatIntegrityError("Participant row was not updated")

        self._write_and_confirm(
            send, lambda: self._values(identity, worksheet_id) == values
        )

    def _append(self, worksheet_id, identity, values, *, rejoining, owner=None):
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
        # Returning means the whole batch, including the participant metadata,
        # was applied: either the write succeeded or its unique guard exists.
        try:
            confirmed = None
            if registration is None and owner is not None:
                confirmed = lambda: self._confirm_participant(
                    owner, worksheet_id, identity
                )
            self._create_once(requests, registration or identity, confirmed=confirmed)
        except APIError as error:
            if _status(error) in (400, 404):
                self._worksheet_properties(worksheet_id)
            raise

    @_storage_errors
    def register(
        self, worksheet_id, user_id, values, *, channel, thread_ts, event_ts=None
    ) -> bool:
        if len(values) != 4 or any(not isinstance(value, str) for value in values):
            raise ValueError("Registration must contain four text values")
        with _WRITES:
            event = self._bound_event(worksheet_id, channel, thread_ts)
            owner = self._participant(event, user_id)
            existing = self._participant_metadata(owner, worksheet_id)
            identity = self._prepare_participant(
                owner, worksheet_id, existing, event_ts, True
            )
            if existing is not None and existing.row is not None:
                previous = self._values(identity, worksheet_id)
                if any(previous):
                    if previous != values:
                        self._write_values(identity, worksheet_id, values)
                    return False
            self._append(
                worksheet_id,
                identity,
                values,
                rejoining=existing is not None,
                owner=owner,
            )
            return True

    @_storage_errors
    def cancel(
        self, worksheet_id, user_id, *, channel, thread_ts, event_ts=None
    ) -> bool:
        with _WRITES:
            event = self._bound_event(worksheet_id, channel, thread_ts)
            owner = self._participant(event, user_id)
            existing = self._participant_metadata(owner, worksheet_id)
            identity = self._prepare_participant(
                owner, worksheet_id, existing, event_ts, False
            )
            if existing is None:
                # Row metadata disappears with its tab; never report a deleted
                # tab as "not registered".
                self._worksheet_properties(worksheet_id)
                if event_ts is not None:
                    self._create_once(
                        [create_participant_state_request(identity, worksheet_id)],
                        identity,
                        confirmed=lambda: self._confirm_participant(
                            owner, worksheet_id, identity
                        ),
                    )
                return False
            if existing.row is None:
                return False
            previous = self._values(identity, worksheet_id)
            if any(previous):
                self._write_values(identity, worksheet_id, ["", "", "", ""])
            return bool(any(previous))
