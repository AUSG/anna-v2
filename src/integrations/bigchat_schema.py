"""Bigchat metadata identities and pure Google Sheets request builders."""

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, TypedDict

EVENT_KEY = "anna.bigchat.v1"
PARTICIPANT_KEY = "anna.participant.v1"
SHEET_KEY = "anna.sheet.v1"


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
    worksheet_id: int, title: str, identity: MetadataIdentity
) -> list[dict[str, object]]:
    return [
        {
            "addSheet": {
                "properties": {
                    "sheetId": worksheet_id,
                    "title": title,
                    "gridProperties": {"rowCount": 100, "columnCount": 4},
                }
            }
        },
        _create_metadata(identity, {"sheetId": worksheet_id}),
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
    worksheet_id: int, identity: MetadataIdentity, values: list[str]
) -> list[dict[str, object]]:
    row_range = {
        "sheetId": worksheet_id,
        "dimension": "ROWS",
        "startIndex": 0,
        "endIndex": 1,
    }
    return [
        {"insertDimension": {"range": row_range, "inheritFromBefore": False}},
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
        _create_metadata(identity, {"dimensionRange": row_range}),
    ]


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
