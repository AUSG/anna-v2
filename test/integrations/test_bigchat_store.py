import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier

import pytest
from gspread.exceptions import APIError

from features.bigchat.errors import (
    BigchatAlreadyCreated,
    BigchatNameConflict,
    BigchatSheetMissing,
    BigchatStorageError,
)
from integrations.bigchat_schema import PARTICIPANT_KEY, SHEET_KEY
from integrations.bigchat_store import BigchatIntegrityError, BigchatStore
from test.fixtures.sheets import SheetsAPI, api_error

CHANNEL, THREAD = "C_TEST", "123.456"
TITLE = "AI 밋업 26-08-20 19:00~21:00"
ALICE = ["Alice", "Company", "a@example.test", "010-1111-1111"]
BOB = ["Bob", "Company", "b@example.test", "010-2222-2222"]
CAROL = ["Carol", "Company", "c@example.test", "010-3333-3333"]


@pytest.fixture
def runtime():
    api = SheetsAPI()
    store = BigchatStore(api)
    sheet = store.create(TITLE, channel=CHANNEL, thread_ts=THREAD).worksheet_id
    return api, store, sheet


def register(store, sheet, user="U_A", values=None):
    return store.register(
        sheet, user, values or ALICE, channel=CHANNEL, thread_ts=THREAD
    )


def cancel(store, sheet, user="U_A"):
    return store.cancel(sheet, user, channel=CHANNEL, thread_ts=THREAD)


def active_rows(api, sheet):
    return [row[:4] for row in api.get_values(sheet) if any(row[:4])]


def reads_since(api, start):
    return [
        suffix
        for method, suffix, _ in api.calls[start:]
        if method == "get" or suffix == "/values:batchGetByDataFilter"
    ]


def test_posted_link_is_known_without_reading_sheets(runtime):
    api, store, sheet = runtime
    start = len(api.calls)
    assert store.sheet_url(CHANNEL, THREAD) == api.get_url(sheet)
    assert api.calls[start:] == []


@pytest.mark.parametrize("parent_exists", [True, False])
def test_absent_event_metadata_is_not_confused_with_an_unavailable_document(
    runtime, monkeypatch, parent_exists
):
    api, store, _ = runtime
    original = api.sheets_request
    calls = []

    def missing(method, suffix, body=None):
        calls.append((method, suffix))
        if suffix.startswith("/developerMetadata/") or not parent_exists:
            raise api_error(404)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", missing)
    if parent_exists:
        assert store.find("C_UNBOUND", THREAD) is None
    else:
        with pytest.raises(BigchatStorageError):
            store.find("C_UNBOUND", THREAD)
    assert calls[-1] == ("get", "?fields=spreadsheetId")
    assert len(calls) == 2


def test_reaction_flow_reuses_the_verified_binding(runtime):
    api, _, sheet = runtime
    # A new store per Slack event: find, then the write for the same thread.
    store = BigchatStore(api)
    lookups = {
        f"/developerMetadata/{identity.metadata_id}"
        for identity in (
            BigchatStore.event_identity(CHANNEL, THREAD),
            BigchatStore.sheet_identity(CHANNEL, THREAD),
        )
    }
    start = len(api.calls)
    assert store.find(CHANNEL, THREAD) == sheet
    assert set(reads_since(api, start)) == lookups

    # Sheets read quotas are per minute, so each write keeps to what it needs:
    # participant metadata, sheet properties and the insertion position.
    start = len(api.calls)
    assert register(store, sheet)
    assert len(reads_since(api, start)) == 3
    assert not lookups & set(reads_since(api, start))

    start = len(api.calls)
    assert cancel(store, sheet)
    assert len(reads_since(api, start)) == 2
    assert not lookups & set(reads_since(api, start))


def test_creation_and_binding_are_atomic_and_survive_lost_response():
    api = SheetsAPI()
    api.fail_after = ":batchUpdate"
    store = BigchatStore(api)
    created = store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    sheet = created.worksheet_id
    assert created.sheet_name == TITLE
    assert created.sheet_url == api.get_url(sheet)
    assert store.get_sheet(sheet) == created
    assert BigchatStore(api).find(CHANNEL, THREAD) == sheet
    assert store.create(TITLE, channel=CHANNEL, thread_ts=THREAD).worksheet_id == sheet
    assert len(api.sheets) == 1
    with pytest.raises(BigchatAlreadyCreated):
        store.create("Another event", channel=CHANNEL, thread_ts=THREAD)


def test_sheet_result_failure_does_not_recreate_the_committed_sheet(monkeypatch):
    api = SheetsAPI()
    store = BigchatStore(api)
    get_url = api.get_url

    def fail_url(_):
        raise RuntimeError("URL unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(api, "get_url", fail_url)
        with pytest.raises(RuntimeError, match="URL unavailable"):
            store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    before = len([call for call in api.calls if call[1] == ":batchUpdate"])
    created = store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    assert created.sheet_url == get_url(created.worksheet_id)
    assert len(api.sheets) == 1
    assert len([call for call in api.calls if call[1] == ":batchUpdate"]) == before


def test_lost_append_response_does_not_duplicate_registration(runtime):
    api, store, sheet = runtime
    api.fail_after = ":batchUpdate"
    assert register(store, sheet)
    assert active_rows(api, sheet) == [ALICE]
    assert not register(BigchatStore(api), sheet)
    assert active_rows(api, sheet) == [ALICE]


def test_profile_changes_update_one_identity_and_cancel_does_not_need_email(runtime):
    api, store, sheet = runtime
    assert register(store, sheet)
    changed = ["Alice", "New company", "new@example.test", "010-9999-9999"]
    assert not register(store, sheet, values=changed)
    assert active_rows(api, sheet) == [changed]
    assert cancel(BigchatStore(api), sheet)
    assert not cancel(store, sheet)
    assert active_rows(api, sheet) == []
    assert register(store, sheet, values=changed)
    assert active_rows(api, sheet) == [changed]


def test_concurrent_cancellations_leave_unrelated_participant(runtime):
    api, store, sheet = runtime
    for user, values in [("U_A", ALICE), ("U_B", BOB), ("U_C", CAROL)]:
        register(store, sheet, user, values)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda user: cancel(BigchatStore(api), sheet, user),
                ["U_A", "U_B", "U_A", "U_B"],
            )
        )
    assert results.count(True) == 2
    assert active_rows(api, sheet) == [CAROL]
    assert len(api.get_values(sheet)) == 3
    assert all("deleteDimension" not in str(body) for _, _, body in api.calls)


def test_row_moves_between_read_and_write_do_not_change_the_target(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    api.before_write = lambda: api.insert_row(sheet, 0, BOB)
    assert cancel(store, sheet)
    assert active_rows(api, sheet) == [BOB]


@pytest.mark.parametrize("operation", ["register", "cancel"])
def test_unbound_or_different_thread_cannot_mutate_sheet(runtime, operation):
    api, store, sheet = runtime
    before = copy.deepcopy((api.sheets, api.metadata))
    kwargs = {"channel": "C_OTHER", "thread_ts": THREAD}
    with pytest.raises(BigchatIntegrityError):
        if operation == "register":
            store.register(sheet, "U_A", ALICE, **kwargs)
        else:
            store.cancel(sheet, "U_A", **kwargs)
    assert (api.sheets, api.metadata) == before
    assert store.find("C_OTHER", THREAD) is None


def test_hash_collision_is_rejected_before_any_write(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    participant = next(
        m for m in api.metadata.values() if m["metadataKey"] == PARTICIPANT_KEY
    )
    participant["metadataValue"] = '["a different event","another user"]'
    before = copy.deepcopy(api.sheets)
    with pytest.raises(BigchatIntegrityError, match="identity conflict"):
        cancel(store, sheet)
    assert api.sheets == before


def test_member_sheet_binding_is_never_used(runtime):
    api, store, _ = runtime
    event = next(m for m in api.metadata.values() if m["metadataKey"] == SHEET_KEY)
    event["location"]["sheetId"] = api.members_worksheet_id
    with pytest.raises(BigchatIntegrityError, match="binding"):
        store.find(CHANNEL, THREAD)


def test_cancellation_reconciles_a_lost_write_response(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    api.fail_after = "/values:batchUpdateByDataFilter"
    assert cancel(store, sheet)
    assert active_rows(api, sheet) == []
    assert len(api.get_values(sheet)) == 1


def test_api_failure_before_commit_is_bounded_and_does_not_create_rows(
    runtime, monkeypatch
):
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", lambda _: None)
    api, store, sheet = runtime
    original = api.sheets_request
    writes = []

    def fail(method, suffix, body=None):
        if suffix == ":batchUpdate":
            writes.append(body)
            raise api_error(503)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", fail)
    with pytest.raises(BigchatStorageError) as caught:
        register(store, sheet)
    assert isinstance(caught.value.__cause__, APIError)
    assert len(writes) == 3
    assert active_rows(api, sheet) == []


def test_partial_batch_failure_rolls_back_inserted_row(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    batch = next(
        body for _, suffix, body in reversed(api.calls) if suffix == ":batchUpdate"
    )
    before = copy.deepcopy((api.sheets, api.metadata))
    with pytest.raises(APIError):
        api.sheets_request("post", ":batchUpdate", batch)
    assert (api.sheets, api.metadata) == before


def test_unique_metadata_guards_concurrent_creators_without_a_shared_lock(
    runtime, monkeypatch
):
    api, _, sheet = runtime
    monkeypatch.setattr(
        "integrations.bigchat_store.write_lock", lambda _: nullcontext()
    )
    barrier = Barrier(2)
    original = api.sheets_request
    reads = []

    def read_together(method, suffix, body=None):
        try:
            return original(method, suffix, body)
        except APIError as error:
            if error.response.status_code == 404 and len(reads) < 2:
                reads.append(1)
                barrier.wait(timeout=3)
            raise

    monkeypatch.setattr(api, "sheets_request", read_together)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(register, BigchatStore(api), sheet) for _ in range(2)]
        for future in futures:
            future.result(timeout=5)
    assert active_rows(api, sheet) == [ALICE]
    assert len(api.get_values(sheet)) == 1


def test_moved_metadata_cannot_write_to_another_sheet(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    api.add_legacy_sheet(456, [BOB])
    participant = next(
        m for m in api.metadata.values() if m["metadataKey"] == PARTICIPANT_KEY
    )

    def move_between_read_and_write():
        participant["location"]["dimensionRange"]["sheetId"] = 456

    api.before_write = move_between_read_and_write
    with pytest.raises(BigchatIntegrityError):
        cancel(store, sheet)
    assert api.get_values(456) == [BOB]


def test_another_creator_with_a_different_title_cannot_be_reported_as_our_event(
    monkeypatch,
):
    api = SheetsAPI()
    store = BigchatStore(api)
    original = api.sheets_request

    def compete(method, suffix, body=None):
        if suffix == ":batchUpdate":
            monkeypatch.setattr(api, "sheets_request", original)
            BigchatStore(api).create("Another event", channel=CHANNEL, thread_ts=THREAD)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", compete)
    with pytest.raises(BigchatAlreadyCreated, match="different bigchat"):
        store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    assert len(api.sheets) == 1
    assert next(iter(api.sheets.values()))["title"] == "Another event"


@pytest.mark.parametrize("existing_count", [0, 1, 2, 3, 6])
def test_new_tab_preserves_the_fourth_position(existing_count):
    api = SheetsAPI()
    previous = list(range(100, 100 + existing_count))
    for sid in previous:
        api.add_legacy_sheet(sid, [])
    created = BigchatStore(api).create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    expected = previous[:]
    expected.insert(min(3, len(previous)), created.worksheet_id)
    assert api.sheet_order == expected


def test_registration_and_rejoining_are_in_processing_order(runtime):
    api, store, sheet = runtime
    for user, values in [("U_A", ALICE), ("U_B", BOB), ("U_C", CAROL)]:
        assert register(store, sheet, user, values)
    assert active_rows(api, sheet) == [ALICE, BOB, CAROL]
    assert cancel(store, sheet, "U_B")
    assert active_rows(api, sheet) == [ALICE, CAROL]
    assert register(store, sheet, "U_B", BOB)
    assert active_rows(api, sheet) == [ALICE, CAROL, BOB]
    assert not register(store, sheet, "U_A", ALICE)
    assert active_rows(api, sheet) == [ALICE, CAROL, BOB]


def test_rejoining_reconciles_lost_response_and_atomic_replay_is_rejected(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    register(store, sheet, "U_B", BOB)
    cancel(store, sheet)
    api.fail_after = ":batchUpdate"
    assert register(store, sheet)
    assert active_rows(api, sheet) == [BOB, ALICE]
    batch = next(
        body for _, suffix, body in reversed(api.calls) if suffix == ":batchUpdate"
    )
    before = copy.deepcopy((api.sheets, api.metadata, api.sheet_order))
    with pytest.raises(APIError):
        api.sheets_request("post", ":batchUpdate", batch)
    assert (api.sheets, api.metadata, api.sheet_order) == before
    assert not register(store, sheet)
    assert active_rows(api, sheet) == [BOB, ALICE]


def test_failed_confirmation_of_committed_rejoin_does_not_replay(runtime, monkeypatch):
    api, store, sheet = runtime
    register(store, sheet)
    cancel(store, sheet)
    original = api.sheets_request
    writes = []
    api.fail_after = ":batchUpdate"

    def fail_confirmation(method, suffix, body=None):
        if writes:
            assert suffix.startswith("/developerMetadata/")
            raise api_error(503)
        if suffix == ":batchUpdate":
            writes.append(body)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", fail_confirmation)
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", lambda _: None)
    with pytest.raises(BigchatStorageError):
        register(store, sheet)
    assert len(writes) == 1
    assert active_rows(api, sheet) == [ALICE]


def test_duplicate_title_does_not_bind_an_unrelated_tab(runtime):
    api, store, sheet = runtime
    before = copy.deepcopy((api.sheets, api.metadata))
    with pytest.raises(BigchatNameConflict):
        store.create(TITLE, channel=CHANNEL, thread_ts="another-thread")
    assert (api.sheets, api.metadata) == before
    assert store.find(CHANNEL, "another-thread") is None
    assert store.find(CHANNEL, THREAD) == sheet


def test_name_taken_between_check_and_creation_has_no_partial_binding():
    api = SheetsAPI()
    store = BigchatStore(api)
    api.before_write = lambda: api.add_legacy_sheet(456, [BOB], title=TITLE)
    with pytest.raises(BigchatNameConflict):
        store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    assert api.get_values(456) == [BOB]
    assert api.metadata == {}
    assert api.sheet_order == [456]


@pytest.mark.parametrize("operation", ["find", "create", "register", "cancel"])
def test_deleted_tab_is_known_and_is_never_recreated(runtime, operation):
    api, store, sheet = runtime
    register(store, sheet)
    api.delete_sheet(sheet)
    before = len(api.calls)
    with pytest.raises(BigchatSheetMissing):
        if operation == "find":
            store.find(CHANNEL, THREAD)
        elif operation == "create":
            store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
        elif operation == "register":
            register(store, sheet)
        else:
            cancel(store, sheet)
    assert api.sheets == {}
    assert len(api.metadata) == 1
    assert all(method == "get" for method, _, _ in api.calls[before:])


def test_deleted_event_cannot_adopt_a_new_tab_with_the_same_name(runtime):
    api, store, sheet = runtime
    api.delete_sheet(sheet)
    replacement = store.create(TITLE, channel=CHANNEL, thread_ts="new-thread")
    assert replacement.worksheet_id != sheet
    with pytest.raises(BigchatSheetMissing):
        store.find(CHANNEL, THREAD)
    assert store.find(CHANNEL, "new-thread") == replacement.worksheet_id


@pytest.mark.parametrize("operation", ["register", "cancel"])
def test_delete_between_read_and_write_is_reported(runtime, operation):
    api, store, sheet = runtime
    register(store, sheet)
    api.before_write = lambda: api.delete_sheet(sheet)
    with pytest.raises(BigchatSheetMissing):
        if operation == "register":
            register(store, sheet, "U_B", BOB)
        else:
            cancel(store, sheet)
    assert api.sheets == {}


def test_deleted_tab_during_grid_read_is_not_a_generic_failure(runtime, monkeypatch):
    api, store, sheet = runtime
    original = api.sheets_request

    def delete_before_read(method, suffix, body=None):
        if suffix == "/values:batchGetByDataFilter":
            api.delete_sheet(sheet)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", delete_before_read)
    with pytest.raises(BigchatSheetMissing):
        register(store, sheet)


def test_full_grid_and_inserted_rows_cannot_overwrite_an_existing_participant(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    api.sheets[sheet]["gridProperties"]["rowCount"] = 1
    api.before_write = lambda: api.insert_row(sheet, 0, CAROL)
    assert register(store, sheet, "U_B", BOB)
    assert sorted(active_rows(api, sheet)) == sorted([ALICE, BOB, CAROL])
    assert cancel(store, sheet)
    assert sorted(active_rows(api, sheet)) == sorted([BOB, CAROL])


def test_cancellation_preserves_notes_outside_participant_columns(runtime):
    api, store, sheet = runtime
    register(store, sheet)
    api.sheets[sheet]["rows"][0].append("operator note")
    assert cancel(store, sheet)
    assert api.get_values(sheet) == [["", "", "", "", "operator note"]]


def test_native_sort_retains_identity_and_rejoin_goes_to_the_end(runtime):
    api, store, sheet = runtime
    register(store, sheet, "U_C", CAROL)
    register(store, sheet, "U_A", ALICE)
    register(store, sheet, "U_B", BOB)
    api.sort_rows(sheet)
    assert active_rows(api, sheet) == [ALICE, BOB, CAROL]
    assert cancel(store, sheet, "U_B")
    assert active_rows(api, sheet) == [ALICE, CAROL]
    assert register(store, sheet, "U_B", BOB)
    assert active_rows(api, sheet) == [ALICE, CAROL, BOB]


def test_values_only_overwrite_is_an_explicit_unsupported_negative_control(runtime):
    api, store, sheet = runtime
    register(store, sheet, "U_C", CAROL)
    register(store, sheet, "U_A", ALICE)
    register(store, sheet, "U_B", BOB)
    api.sort_rows(sheet, values_only=True)
    # Values changed while identities stayed on their original rows. This must
    # remain a visible limitation, never evidence that arbitrary edits are safe.
    assert cancel(store, sheet, "U_C")
    assert active_rows(api, sheet) == [BOB, CAROL]
