import copy

import pytest
from gspread.exceptions import APIError
from requests.exceptions import ConnectionError, RequestException

from features.bigchat.errors import BigchatStorageError
from integrations.bigchat_store import BigchatStore
from test.fixtures.sheets import SheetsAPI, api_error

CHANNEL, THREAD = "C_TEST", "123.456"
TITLE = "AI 밋업 26-08-20 19:00~21:00"
ALICE = ["Alice", "Company", "a@example.test", "000"]
BOB = ["Bob", "Company", "b@example.test", "111"]
CAROL = ["Carol", "Company", "c@example.test", "222"]
CONTEXT = {"channel": CHANNEL, "thread_ts": THREAD}


@pytest.fixture
def runtime():
    api = SheetsAPI()
    store = BigchatStore(api)
    sid = store.create(TITLE, **CONTEXT).worksheet_id
    store.register(sid, "U_A", ALICE, **CONTEXT)
    store.register(sid, "U_B", BOB, **CONTEXT)
    return api, store, sid


def rows(api, sid):
    return [row for row in api.get_values(sid) if any(row)]


def is_target_read(kind, suffix, body):
    if kind == "metadata":
        return suffix.startswith("/developerMetadata/")
    if kind == "properties":
        return suffix == "?fields=sheets.properties"
    if suffix != "/values:batchGetByDataFilter":
        return False
    return ("gridRange" in body["dataFilters"][0]) == (kind == "grid")


@pytest.mark.parametrize("kind", ["metadata", "properties", "values", "grid"])
@pytest.mark.parametrize("status", [429, 503, None])
def test_transient_reads_recover_before_the_operation_proceeds(
    runtime, monkeypatch, kind, status
):
    api, store, sid = runtime
    original = api.sheets_request
    attempts, delays = [], []
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", delays.append)

    def flaky(method, suffix, body=None):
        if is_target_read(kind, suffix, body):
            attempts.append(suffix)
            if len(attempts) < 3:
                raise api_error(status) if status else ConnectionError("unavailable")
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", flaky)
    if kind == "metadata":
        assert store.find(**CONTEXT) == sid
        assert rows(api, sid) == [ALICE, BOB]
    elif kind == "properties":
        assert store.get_sheet(sid).sheet_name == TITLE
        assert rows(api, sid) == [ALICE, BOB]
    elif kind == "values":
        assert store.cancel(sid, "U_A", **CONTEXT)
        assert rows(api, sid) == [BOB]
    else:
        assert store.register(sid, "U_C", CAROL, **CONTEXT)
        assert rows(api, sid) == [ALICE, BOB, CAROL]
    assert attempts[:3] == [attempts[0]] * 3
    assert delays == ([5, 10] if status == 429 else [1, 2])


@pytest.mark.parametrize(
    "status,limit,expected_delays",
    [
        (400, 1, []),
        (401, 1, []),
        (403, 1, []),
        (408, 3, [1, 2]),
        (429, 5, [5, 10, 20, 30]),
        (500, 3, [1, 2]),
        (502, 3, [1, 2]),
        (503, 3, [1, 2]),
        (504, 3, [1, 2]),
    ],
)
def test_failed_reads_stop_at_the_limit_without_writing(
    runtime, monkeypatch, status, limit, expected_delays
):
    api, store, sid = runtime
    attempts, delays = [], []
    before = copy.deepcopy((api.sheets, api.metadata))
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", delays.append)

    def failed_read(method, suffix, body=None):
        assert method == "get"
        attempts.append(suffix)
        raise api_error(status)

    monkeypatch.setattr(api, "sheets_request", failed_read)
    with pytest.raises(BigchatStorageError) as caught:
        store.cancel(sid, "U_A", **CONTEXT)
    assert isinstance(caught.value.__cause__, APIError)
    assert caught.value.__cause__.response.status_code == status
    assert len(attempts) == limit
    assert delays == expected_delays
    assert (api.sheets, api.metadata) == before


def test_read_retries_share_one_time_budget_per_operation(runtime, monkeypatch):
    api, store, sid = runtime
    original = api.sheets_request
    clock, delays = [0.0], []
    failures = {"/developerMetadata/": 3, "/values:batchGetByDataFilter": 99}

    def sleep(seconds):
        delays.append(seconds)
        clock[0] += seconds

    def rate_limited(method, suffix, body=None):
        for prefix, remaining in failures.items():
            if suffix.startswith(prefix) and remaining:
                failures[prefix] -= 1
                raise api_error(429)
        return original(method, suffix, body)

    monkeypatch.setattr("integrations.bigchat_store.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("integrations.bigchat_store.time.sleep", sleep)
    monkeypatch.setattr(api, "sheets_request", rate_limited)
    with pytest.raises(BigchatStorageError):
        store.cancel(sid, "U_A", **CONTEXT)
    # The participant read spent 35s, so the value read stops before a 30s wait
    # would pass the 90s budget, and nothing is written.
    assert delays == [5, 10, 20, 5, 10, 20]
    assert rows(api, sid) == [ALICE, BOB]

    # The next operation starts with a fresh budget.
    clock[0], delays[:] = 1000.0, []
    failures.update({"/developerMetadata/": 1, "/values:batchGetByDataFilter": 0})
    assert store.find(**CONTEXT) == sid
    assert delays == [5]


def test_missing_metadata_is_not_retried(runtime, monkeypatch):
    api, store, _ = runtime
    delays = []
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", delays.append)
    before = len(api.calls)
    assert store.find("C_UNBOUND", THREAD) is None
    assert len(api.calls) == before + 2
    assert api.calls[-1][1] == "?fields=spreadsheetId"
    assert delays == []


@pytest.mark.parametrize("operation", ["create", "register", "cancel", "rejoin"])
@pytest.mark.parametrize("recovers", [True, False])
def test_uncertain_writes_only_retry_the_confirmation_reads(
    runtime, monkeypatch, operation, recovers
):
    api, store, sid = runtime
    if operation == "rejoin":
        store.cancel(sid, "U_A", **CONTEXT)
    suffix_to_lose = (
        "/values:batchUpdateByDataFilter" if operation == "cancel" else ":batchUpdate"
    )
    api.fail_after = suffix_to_lose
    original = api.sheets_request
    recovering = False
    reads, writes, delays = [], [], []
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", delays.append)

    def interrupted(method, suffix, body=None):
        nonlocal recovering
        if recovering:
            assert method == "get" or suffix == "/values:batchGetByDataFilter"
            reads.append(suffix)
            if not recovers or len(reads) < 3:
                raise api_error(503)
            recovering = False
        if suffix == suffix_to_lose:
            writes.append(suffix)
        try:
            return original(method, suffix, body)
        except RequestException:
            recovering = True
            raise

    def perform():
        if operation == "create":
            return store.create("Other event", channel="C_OTHER", thread_ts=THREAD)
        if operation == "register":
            return store.register(sid, "U_C", CAROL, **CONTEXT)
        if operation == "rejoin":
            return store.register(sid, "U_A", ALICE, **CONTEXT)
        return store.cancel(sid, "U_A", **CONTEXT)

    monkeypatch.setattr(api, "sheets_request", interrupted)
    if recovers:
        assert perform()
    else:
        with pytest.raises(BigchatStorageError):
            perform()
    assert len(reads) == 3
    assert len(writes) == 1
    assert delays == [1, 2]
    expected_rows = {
        "create": [ALICE, BOB],
        "register": [ALICE, BOB, CAROL],
        "cancel": [BOB],
        "rejoin": [BOB, ALICE],
    }
    assert rows(api, sid) == expected_rows[operation]
    assert len(api.sheets) == (2 if operation == "create" else 1)
