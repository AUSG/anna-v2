"""Persisted reaction ordering and participant metadata validation.

Unversioned records are the initial creation-time snapshot. A live Slack event
always takes precedence over that snapshot, even in a fresh process/store.
"""

import json
import re
from dataclasses import dataclass
from decimal import Decimal

from features.bigchat.errors import BigchatIntegrityError, ReactionSuperseded
from integrations.bigchat_schema import MetadataIdentity, participant_filter


def timestamp(value: str) -> Decimal:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+\.[0-9]+", value):
        raise BigchatIntegrityError("Invalid reaction event timestamp")
    return Decimal(value)


def reaction_identity(owner: MetadataIdentity, event_ts, active, token):
    if event_ts is None:
        return owner
    timestamp(event_ts)
    parts = json.loads(owner.value)
    return MetadataIdentity(
        owner.metadata_id,
        owner.key,
        json.dumps([*parts, event_ts, active, token], separators=(",", ":")),
    )


@dataclass(frozen=True)
class Participant:
    identity: MetadataIdentity
    user_id: str
    event_ts: str | None
    active: bool | None
    row: int | None

    @classmethod
    def read(cls, metadata, owner: MetadataIdentity, worksheet_id):
        if (
            metadata.get("metadataId") != owner.metadata_id
            or metadata.get("metadataKey") != owner.key
            or metadata.get("visibility") != "DOCUMENT"
        ):
            raise BigchatIntegrityError("Participant identity conflict")
        try:
            parts = json.loads(metadata["metadataValue"])
        except (KeyError, TypeError, ValueError) as error:
            raise BigchatIntegrityError("Invalid participant state") from error
        expected = json.loads(owner.value)
        if (
            not isinstance(parts, list)
            or len(parts) not in (2, 5)
            or parts[:2] != expected
        ):
            raise BigchatIntegrityError("Participant identity conflict")
        event_ts, active = None, None
        if len(parts) == 5:
            event_ts, active, token = parts[2:]
            timestamp(event_ts)
            if (
                type(active) is not bool
                or not isinstance(token, str)
                or not re.fullmatch(r"[0-9a-f]{32}", token)
            ):
                raise BigchatIntegrityError("Invalid participant revision")
        location = {
            k: v for k, v in metadata.get("location", {}).items() if k != "locationType"
        }
        if location == {"sheetId": worksheet_id} and event_ts is not None:
            row = None  # cancellation before the first registration
        else:
            area = location.get("dimensionRange", {})
            row = area.get("startIndex")
            if (
                set(location) != {"dimensionRange"}
                or area.get("sheetId") != worksheet_id
                or area.get("dimension") != "ROWS"
                or type(row) is not int
                or row < 0
                or area.get("endIndex") != row + 1
            ):
                raise BigchatIntegrityError(
                    "Participant metadata is not on the bound worksheet row"
                )
        return cls(
            MetadataIdentity(owner.metadata_id, owner.key, metadata["metadataValue"]),
            expected[1],
            event_ts,
            active,
            row,
        )

    def accepts(self, event_ts, active):
        if self.event_ts is None:
            return
        if event_ts is None or timestamp(event_ts) < timestamp(self.event_ts):
            raise ReactionSuperseded("A newer reaction has already been recorded")
        if timestamp(event_ts) == timestamp(self.event_ts) and active != self.active:
            raise BigchatIntegrityError("Conflicting reactions have the same timestamp")


def transition_request(
    previous: MetadataIdentity, current: MetadataIdentity, worksheet_id
):
    return {
        "updateDeveloperMetadata": {
            "dataFilters": [participant_filter(previous, worksheet_id)],
            "developerMetadata": {"metadataValue": current.value},
            "fields": "metadataValue",
        }
    }
