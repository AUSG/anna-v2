import copy
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier

import pytest
from gspread.exceptions import APIError
from requests.exceptions import ConnectionError, RequestException

from integrations.bigchat_schema import EVENT_KEY, PARTICIPANT_KEY
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
    return [row for row in api.get_values(sheet) if any(row)]


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
    with pytest.raises(BigchatIntegrityError):
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
    assert api.get_values(sheet) == [changed]


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
    event = next(m for m in api.metadata.values() if m["metadataKey"] == EVENT_KEY)
    event["location"]["sheetId"] = api.members_worksheet_id
    with pytest.raises(BigchatIntegrityError, match="protected"):
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
    monkeypatch.setattr("integrations.bigchat_store.time.sleep", lambda _: None)
    api, store, sheet = runtime
    original = api.sheets_request
    writes = []

    def fail(method, suffix, body=None):
        if suffix == ":batchUpdate":
            writes.append(body)
            raise api_error(503)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", fail)
    with pytest.raises(APIError):
        register(store, sheet)
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
    monkeypatch.setattr("integrations.bigchat_store._WRITES", nullcontext())
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
    with pytest.raises(BigchatIntegrityError, match="different bigchat"):
        store.create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    assert len(api.sheets) == 1
    assert next(iter(api.sheets.values()))["title"] == "Another event"


@pytest.mark.parametrize("read_kind", ["metadata", "values"])
@pytest.mark.parametrize("status", [429, 503, None])
def test_transient_reads_recover_before_proceeding(
    runtime, monkeypatch, read_kind, status
):
    api, store, sheet = runtime
    register(store, sheet)
    original = api.sheets_request
    attempts, delays = [], []
    monkeypatch.setattr("integrations.bigchat_store.time.sleep", delays.append)

    def flaky_read(method, suffix, body=None):
        is_read = (
            method == "get"
            if read_kind == "metadata"
            else suffix == "/values:batchGetByDataFilter"
        )
        if is_read:
            attempts.append(suffix)
            if len(attempts) < 3:
                raise (
                    api_error(status)
                    if status is not None
                    else ConnectionError("unavailable")
                )
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", flaky_read)
    if read_kind == "metadata":
        assert store.find(CHANNEL, THREAD) == sheet
        assert active_rows(api, sheet) == [ALICE]
    else:
        assert cancel(store, sheet)
        assert active_rows(api, sheet) == []
    assert len(attempts) == 3
    assert delays == [1, 2]


@pytest.mark.parametrize("read_kind", ["metadata", "values"])
@pytest.mark.parametrize("status, limit", [(403, 1), (429, 3), (503, 3)])
def test_read_failures_are_bounded_and_never_write(
    runtime, monkeypatch, read_kind, status, limit
):
    api, store, sheet = runtime
    register(store, sheet)
    original = api.sheets_request
    attempts, delays, writes = [], [], []
    before = copy.deepcopy((api.sheets, api.metadata))
    monkeypatch.setattr("integrations.bigchat_store.time.sleep", delays.append)

    def failed_read(method, suffix, body=None):
        is_read = (
            method == "get"
            if read_kind == "metadata"
            else suffix == "/values:batchGetByDataFilter"
        )
        if is_read:
            attempts.append(suffix)
            raise api_error(status)
        if suffix in (":batchUpdate", "/values:batchUpdateByDataFilter"):
            writes.append(suffix)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", failed_read)
    with pytest.raises(APIError) as error:
        cancel(store, sheet)
    assert error.value.response.status_code == status
    assert len(attempts) == limit
    assert delays == ([] if limit == 1 else [1, 2])
    assert writes == []
    assert (api.sheets, api.metadata) == before


def test_missing_metadata_returns_without_retry(runtime, monkeypatch):
    api, store, _ = runtime
    delays = []
    monkeypatch.setattr("integrations.bigchat_store.time.sleep", delays.append)
    before = len(api.calls)
    assert store.find("C_OTHER", THREAD) is None
    assert len(api.calls) == before + 1
    assert delays == []


@pytest.mark.parametrize("operation", ["create", "register", "cancel"])
@pytest.mark.parametrize("recovers", [True, False])
def test_uncertain_writes_only_retry_confirmation_reads(
    runtime, monkeypatch, operation, recovers
):
    api, store, sheet = runtime
    if operation == "cancel":
        register(store, sheet)
    write_suffix = (
        "/values:batchUpdateByDataFilter" if operation == "cancel" else ":batchUpdate"
    )
    api.fail_after = write_suffix
    original = api.sheets_request
    recovering = False
    reads, writes, delays = [], [], []
    monkeypatch.setattr("integrations.bigchat_store.time.sleep", delays.append)

    def interrupted(method, suffix, body=None):
        nonlocal recovering
        if recovering:
            reads.append(suffix)
            assert method == "get" or suffix == "/values:batchGetByDataFilter"
            if not recovers or len(reads) < 3:
                raise api_error(503)
            recovering = False
        if suffix == write_suffix:
            writes.append(suffix)
        try:
            return original(method, suffix, body)
        except RequestException:
            assert suffix == write_suffix
            recovering = True
            raise

    def perform():
        if operation == "create":
            return store.create(TITLE, channel="C_OTHER", thread_ts=THREAD)
        if operation == "register":
            return register(store, sheet)
        return cancel(store, sheet)

    monkeypatch.setattr(api, "sheets_request", interrupted)
    if recovers:
        assert perform()
    else:
        with pytest.raises(APIError) as error:
            perform()
        assert error.value.response.status_code == 503
    assert len(reads) == 3
    assert len(writes) == 1
    assert delays == [1, 2]
    if operation == "create":
        assert len(api.sheets) == 2
    else:
        assert active_rows(api, sheet) == ([ALICE] if operation == "register" else [])
