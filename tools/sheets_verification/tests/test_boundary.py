import copy
import json
from types import SimpleNamespace

import pytest
import requests

from integrations.bigchat_participant import reaction_identity, transition_request
from integrations.bigchat_store import BigchatStore
from test.fixtures.sheets import SheetsAPI
from tools.sheets_verification.boundary import (
    BoundaryError,
    SheetsTestBoundary,
    attach_boundary,
)


def policy_for(store, role="create"):
    policy = SheetsTestBoundary("explicit-test-document", 0, "ANNA_TEST_")
    event = store.event_identity("C_TEST", "1.2")
    sheet = store.sheet_identity("C_TEST", "1.2")
    policy.add_sheet(sheet.metadata_id, "ANNA_TEST_fixture", role)
    policy.add_metadata(event.to_api(), sheet.metadata_id, "document")
    policy.add_metadata(sheet.to_api(), sheet.metadata_id, "sheet")
    for user in ["U_A", "U_B"]:
        policy.add_metadata(
            store._participant(event, user).to_api(), sheet.metadata_id, "row"
        )
    return policy, sheet.metadata_id


def test_boundary_accepts_the_actual_store_contract_including_rejoining(monkeypatch):
    api = SheetsAPI()
    store = BigchatStore(api)
    policy, sid = policy_for(store)
    policy.arm([], [])
    original = api.sheets_request

    def guarded(method, suffix, body=None):
        policy.check(method, policy.base + suffix, body)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", guarded)
    kw = {"channel": "C_TEST", "thread_ts": "1.2"}
    assert store.create("ANNA_TEST_fixture", **kw).worksheet_id == sid
    for user in ["U_A", "U_B"]:
        assert store.register(sid, user, [user, "company", "email", "phone"], **kw)
    assert store.cancel(sid, "U_A", **kw)
    assert store.register(sid, "U_A", ["U_A", "company", "email", "phone"], **kw)
    assert store.cancel(sid, "U_A", **kw, event_ts="200.000001")
    assert store.register(
        sid, "U_A", ["U_A", "company", "email", "phone"], **kw, event_ts="200.000002"
    )
    assert store.cancel(sid, "U_B", **kw, event_ts="200.000003")
    assert store.active_user_ids(sid) == ["U_A"]


@pytest.mark.parametrize("fault", ["owner", "sheet", "broad", "location", "id"])
def test_revision_updates_remain_confined_to_one_planned_participant(fault):
    store = BigchatStore(SheetsAPI())
    policy, sid = policy_for(store)
    policy.arm([], [])
    owner = store._participant(store.event_identity("C_TEST", "1.2"), "U_A")
    revision = reaction_identity(owner, "200.000001", False, "a" * 32)
    request = transition_request(owner, revision, sid)
    assert (
        policy.check("POST", policy.base + ":batchUpdate", {"requests": [request]})
        == "write"
    )
    update = request["updateDeveloperMetadata"]
    lookup = update["dataFilters"][0]["developerMetadataLookup"]
    if fault == "owner":
        parts = json.loads(revision.value)
        parts[1] = "U_OTHER"
        update["developerMetadata"]["metadataValue"] = json.dumps(parts)
    elif fault == "sheet":
        lookup["metadataLocation"]["sheetId"] = 0
    elif fault == "broad":
        del lookup["metadataId"]
    elif fault == "location":
        update["fields"] = "location"
    else:
        update["developerMetadata"]["metadataId"] = 123
    with pytest.raises(BoundaryError):
        policy.check("POST", policy.base + ":batchUpdate", {"requests": [request]})


@pytest.mark.parametrize(
    "target",
    [
        "different_document",
        "other_host",
        "source_copy",
        "existing_tab",
        "delete_existing",
        "delete_normal_test_tab",
        "unfiltered_write",
        "metadata_elsewhere",
        "copy_to_other_document",
        "broad_metadata_delete",
        "rename_tab",
        "not_armed",
    ],
)
def test_forbidden_requests_are_blocked_before_transport(target):
    store = BigchatStore(SheetsAPI())
    policy, sid = policy_for(store)
    if target != "not_armed":
        policy.arm([], [])
    method, url = "POST", policy.base + ":batchUpdate"
    body = {
        "requests": [
            {
                "sortRange": {
                    "range": {"sheetId": sid},
                    "sortSpecs": [{"dimensionIndex": 0, "sortOrder": "ASCENDING"}],
                }
            }
        ]
    }
    if target == "different_document":
        url = url.replace("explicit-test-document", "production-document")
    elif target == "other_host":
        url = url.replace("sheets.googleapis.com", "example.com")
    elif target in {"source_copy", "existing_tab"}:
        body["requests"][0]["sortRange"]["range"]["sheetId"] = (
            0 if target == "source_copy" else 999
        )
    elif target in {"delete_existing", "delete_normal_test_tab"}:
        body = {
            "requests": [
                {
                    "deleteSheet": {
                        "sheetId": 999 if target == "delete_existing" else sid
                    }
                }
            ]
        }
    elif target == "unfiltered_write":
        method, url, body = (
            "PUT",
            policy.base + "/values/'source'!A1:D1?valueInputOption=RAW",
            {"majorDimension": "ROWS", "values": [["", "", "", ""]]},
        )
    elif target == "metadata_elsewhere":
        fields = next(
            fields for fields, _, kind in policy.metadata.values() if kind == "row"
        )
        body = {
            "requests": [
                {
                    "createDeveloperMetadata": {
                        "developerMetadata": {
                            **fields,
                            "visibility": "DOCUMENT",
                            "location": {
                                "dimensionRange": {
                                    "sheetId": 0,
                                    "dimension": "ROWS",
                                    "startIndex": 0,
                                    "endIndex": 1,
                                }
                            },
                        }
                    }
                }
            ]
        }
    elif target == "copy_to_other_document":
        url, body = (
            policy.base + f"/sheets/{sid}:copyTo",
            {"destinationSpreadsheetId": "production-document"},
        )
    elif target == "broad_metadata_delete":
        body = {
            "requests": [
                {
                    "deleteDeveloperMetadata": {
                        "dataFilter": {
                            "developerMetadataLookup": {
                                "metadataKey": "anna.participant.v1"
                            }
                        }
                    }
                }
            ]
        }
    elif target == "rename_tab":
        body = {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": sid, "title": "source"},
                        "fields": "title",
                    }
                }
            ]
        }
    sent = []
    session = SimpleNamespace(
        send=lambda request, **kw: (
            sent.append(request) or SimpleNamespace(status_code=200)
        )
    )
    attach_boundary(session, policy, lambda *a: None, interval=0)
    with pytest.raises(BoundaryError):
        session.send(requests.Request(method, url, json=body).prepare())
    assert sent == []


def test_existing_identity_collision_keeps_writes_disabled():
    policy, sid = policy_for(BigchatStore(SheetsAPI()))
    with pytest.raises(BoundaryError):
        policy.arm([sid], [])
    assert not policy.armed
    with pytest.raises(BoundaryError):
        policy.arm([], list(policy.metadata))
    assert not policy.armed


def test_moved_participant_filter_cannot_target_the_preserved_copy():
    policy, sid = policy_for(BigchatStore(SheetsAPI()))
    policy.arm([], [])
    fields = next(
        fields for fields, _, kind in policy.metadata.values() if kind == "row"
    )
    lookup = {
        **fields,
        "visibility": "DOCUMENT",
        "locationType": "ROW",
        "metadataLocation": {"sheetId": sid},
        "locationMatchingStrategy": "INTERSECTING_LOCATION",
    }
    body: dict = {
        "valueInputOption": "RAW",
        "data": [
            {
                "dataFilter": {"developerMetadataLookup": lookup},
                "majorDimension": "ROWS",
                "values": [["", "", "", ""]],
            }
        ],
    }
    assert (
        policy.check("POST", policy.base + "/values:batchUpdateByDataFilter", body)
        == "write"
    )
    moved = copy.deepcopy(body)
    moved["data"][0]["dataFilter"]["developerMetadataLookup"]["metadataLocation"][
        "sheetId"
    ] = 0
    with pytest.raises(BoundaryError):
        policy.check("POST", policy.base + "/values:batchUpdateByDataFilter", moved)
