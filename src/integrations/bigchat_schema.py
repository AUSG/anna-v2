"""Bigchat metadata identities and pure Google Sheets request builders."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, TypedDict

EVENT_KEY = "anna.bigchat.v1"
PARTICIPANT_KEY = "anna.participant.v1"
SHEET_KEY = "anna.sheet.v1"
REGISTRATION_KEY = "anna.registration.v1"


class MetadataFields(TypedDict):
    metadataId: int
    metadataKey: str
    metadataValue: str


class RowMetadataLookup(MetadataFields):
    visibility: Literal["DOCUMENT"]
    locationType: Literal["ROW"]
    metadataLocation: dict[str, int]
    locationMatchingStrategy: Literal["INTERSECTING_LOCATION"]


class MetadataFilter(TypedDict):
    developerMetadataLookup: RowMetadataLookup


@dataclass(frozen=True)
class MetadataIdentity:
    metadata_id: int
    key: str
    value: str

    @classmethod
    def from_parts(cls, key: str, *parts: str) -> MetadataIdentity:
        if any(not isinstance(part, str) or not part for part in parts):
            raise ValueError("Bigchat identity fields must be nonempty strings")
        value = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(f"{key}:{value}".encode()).digest()
        # Persisted positive int32 IDs: keep this encoding stable. The store
        # compares all identity fields on reads to reject hash collisions.
        metadata_id = int.from_bytes(digest[:4], "big") & 0x7FFFFFFF or 1
        return cls(metadata_id, key, value)

    def to_api(self) -> MetadataFields:
        return {
            "metadataId": self.metadata_id,
            "metadataKey": self.key,
            "metadataValue": self.value,
        }


def _create_metadata(
    identity: MetadataIdentity, location: dict[str, object]
) -> dict[str, object]:
    return {
        "createDeveloperMetadata": {
            "developerMetadata": {
                **identity.to_api(),
                "visibility": "DOCUMENT",
                "location": location,
            }
        }
    }


def create_sheet_requests(
    title: str,
    event: MetadataIdentity,
    sheet: MetadataIdentity,
    index: int,
) -> list[dict[str, object]]:
    worksheet_id = sheet.metadata_id
    return [
        {
            "addSheet": {
                "properties": {
                    "sheetId": worksheet_id,
                    "title": title,
                    "index": index,
                    "gridProperties": {"rowCount": 100, "columnCount": 4},
                }
            }
        },
        # The document record survives deletion of the tab and its row metadata.
        _create_metadata(event, {"spreadsheet": True}),
        _create_metadata(sheet, {"sheetId": worksheet_id}),
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
    ]


def create_participant_requests(
    worksheet_id: int,
    identity: MetadataIdentity,
    values: list[str],
    row_index: int,
    grid_rows: int,
    registration: MetadataIdentity | None = None,
) -> list[dict[str, object]]:
    row_range = {
        "sheetId": worksheet_id,
        "dimension": "ROWS",
        "startIndex": row_index,
        "endIndex": row_index + 1,
    }
    # Inserting a fresh row never overwrites a row that moved after the read.
    # A completely full grid needs one new row before it can be addressed.
    requests: list[dict[str, object]] = []
    if row_index == grid_rows:
        requests.append(
            {
                "appendDimension": {
                    "sheetId": worksheet_id,
                    "dimension": "ROWS",
                    "length": 1,
                }
            }
        )
    requests.extend(
        [
            {"insertDimension": {"range": row_range, "inheritFromBefore": False}},
            {
                "updateCells": {
                    "start": {
                        "sheetId": worksheet_id,
                        "rowIndex": row_index,
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
        ]
    )
    if registration is not None:
        # Rejoining gets a new position. This extra unique ID fences the whole
        # batch: replay must fail atomically before another row can be inserted.
        requests.extend(
            [
                _create_metadata(registration, {"dimensionRange": row_range}),
                {
                    "deleteDeveloperMetadata": {
                        "dataFilter": _row_filter(identity, worksheet_id)
                    }
                },
            ]
        )
    requests.append(_create_metadata(identity, {"dimensionRange": row_range}))
    return requests


def _row_filter(identity: MetadataIdentity, worksheet_id: int) -> MetadataFilter:
    return {
        "developerMetadataLookup": {
            **identity.to_api(),
            "visibility": "DOCUMENT",
            "locationType": "ROW",
            "metadataLocation": {"sheetId": worksheet_id},
            "locationMatchingStrategy": "INTERSECTING_LOCATION",
        }
    }


def read_values_request(
    identity: MetadataIdentity, worksheet_id: int
) -> dict[str, object]:
    return {
        "dataFilters": [_row_filter(identity, worksheet_id)],
        "valueRenderOption": "UNFORMATTED_VALUE",
    }


def write_values_request(
    identity: MetadataIdentity, worksheet_id: int, values: list[str]
) -> dict[str, object]:
    return {
        "valueInputOption": "RAW",
        "data": [
            {
                "dataFilter": _row_filter(identity, worksheet_id),
                "majorDimension": "ROWS",
                "values": [values],
            }
        ],
    }
