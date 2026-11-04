from dataclasses import FrozenInstanceError

import pytest

from integrations.bigchat_schema import (
    EVENT_KEY,
    PARTICIPANT_KEY,
    SHEET_KEY,
    MetadataIdentity,
)


@pytest.mark.parametrize(
    "key, parts, metadata_id, value",
    [
        (EVENT_KEY, ("C_TEST", "123.456"), 2037843190, '["C_TEST","123.456"]'),
        (SHEET_KEY, ("C_TEST", "123.456"), 2006075524, '["C_TEST","123.456"]'),
        (PARTICIPANT_KEY, ("2037843190", "U_A"), 942815500, '["2037843190","U_A"]'),
        (EVENT_KEY, ("C_테스트", "123.456"), 151585990, '["C_테스트","123.456"]'),
    ],
)
def test_identity_encoding_remains_compatible_with_stored_records(
    key, parts, metadata_id, value
):
    # Fixed values captured before the schema extraction, not derived by this test.
    identity = MetadataIdentity.from_parts(key, *parts)
    assert identity.to_api() == {
        "metadataId": metadata_id,
        "metadataKey": key,
        "metadataValue": value,
    }
    payload = identity.to_api()
    payload["metadataId"] = 0
    assert identity.metadata_id == metadata_id


@pytest.mark.parametrize("part", ["", None, 123, []])
def test_invalid_identity_parts_are_rejected(part):
    with pytest.raises(ValueError, match="nonempty strings"):
        MetadataIdentity.from_parts(EVENT_KEY, "C_TEST", part)


@pytest.mark.parametrize("field", ["metadata_id", "key", "value"])
def test_identity_cannot_change_after_creation(field):
    identity = MetadataIdentity.from_parts(EVENT_KEY, "C_TEST", "123.456")
    with pytest.raises(FrozenInstanceError):
        setattr(identity, field, None)
