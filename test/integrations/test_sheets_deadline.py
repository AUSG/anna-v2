"""Deadline regressions through the store, real locks and installed SDKs."""

import json
from concurrent.futures import ThreadPoolExecutor

import gspread
import pytest
from google.auth.credentials import AnonymousCredentials
from requests import Response
from requests.adapters import HTTPAdapter
from requests.exceptions import Timeout

from features.bigchat.errors import BigchatStorageError
from integrations import bigchat_store, sheets_retry
from integrations.bigchat_store import BigchatStore
from integrations.google_sheets import GoogleSpreadsheetClient
from integrations.sheets_http import SheetsHTTPClient
from test.fixtures.sheets import SheetsAPI, api_error

CONTEXT = {"channel": "C_BUDGET", "thread_ts": "123.456"}
VALUES = ["name", "company", "user@example.test", "phone"]


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = 0.0

        def sleep(self, seconds):
            self.now += seconds

    clock = Clock()
    monkeypatch.setattr(sheets_retry.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(sheets_retry.time, "sleep", clock.sleep)
    return clock


@pytest.mark.parametrize("operation", ["create", "register", "cancel"])
@pytest.mark.parametrize("status", [429, 503])
def test_slow_writes_and_confirmation_cannot_restart_the_budget(
    clock, monkeypatch, operation, status
):
    api = SheetsAPI()
    store = BigchatStore(api)
    sid = store.create("event", **CONTEXT).worksheet_id
    store.register(sid, "U_A", VALUES, **CONTEXT)
    original = api.sheets_request
    calls = []

    def slow(method, suffix, body=None):
        left = sheets_retry.remaining_seconds()
        calls.append((suffix, clock.now, left))
        clock.sleep(min(20, left))
        if left <= 20:
            raise Timeout("response exceeded the remaining request timeout")
        if suffix in {":batchUpdate", "/values:batchUpdateByDataFilter"}:
            raise api_error(status)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", slow)
    with pytest.raises(BigchatStorageError):
        if operation == "create":
            store.create("new", channel="C_NEW", thread_ts="123.456")
        elif operation == "register":
            store.register(sid, "U_B", VALUES, **CONTEXT)
        else:
            store.cancel(sid, "U_A", **CONTEXT)
    writes = [
        at
        for suffix, at, _ in calls
        if suffix in {":batchUpdate", "/values:batchUpdateByDataFilter"}
    ]
    assert writes and all(at < 90 for at in writes)
    assert clock.now <= 90
    assert all(left == 90 - at for _, at, left in calls)
    assert api.get_values(sid) == [VALUES]
    assert len(api.sheets) == 1
    assert sheets_retry.remaining_seconds() is None


@pytest.mark.parametrize("operation", ["register", "cancel"])
def test_a_write_finished_past_the_deadline_is_not_reported_as_a_failure(
    clock, monkeypatch, operation
):
    api = SheetsAPI()
    store = BigchatStore(api)
    sid = store.create("event", **CONTEXT).worksheet_id
    if operation == "cancel":
        store.register(sid, "U_A", VALUES, **CONTEXT)
    original = api.sheets_request

    def committed_late(method, suffix, body=None):
        response = original(method, suffix, body)
        if suffix in {":batchUpdate", "/values:batchUpdateByDataFilter"}:
            clock.sleep(95)  # applied, but the reply arrives past the budget
        return response

    monkeypatch.setattr(api, "sheets_request", committed_late)
    if operation == "register":
        assert store.register(sid, "U_A", VALUES, **CONTEXT) is True
        assert api.get_values(sid) == [VALUES]
    else:
        assert store.cancel(sid, "U_A", **CONTEXT) is True
        assert api.get_values(sid) == [["", "", "", ""]]
    assert sheets_retry.remaining_seconds() is None


def test_waiting_for_the_real_write_lock_expires_without_touching_sheets(monkeypatch):
    api = SheetsAPI()
    store = BigchatStore(api)
    sid = store.create("event", **CONTEXT).worksheet_id
    before = len(api.calls)
    monkeypatch.setattr(sheets_retry, "OPERATION_SECONDS", 0.03)
    with bigchat_store._WRITES, ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(store.register, sid, "U_A", VALUES, **CONTEXT)
        with pytest.raises(BigchatStorageError) as error:
            result.result(timeout=2)
    assert isinstance(error.value.__cause__, sheets_retry.OperationTimeout)
    assert len(api.calls) == before
    assert api.get_values(sid) == []


def test_no_network_request_after_a_lock_consumes_the_budget(clock, monkeypatch):
    api = SheetsAPI()
    store = BigchatStore(api)
    sid = store.create("event", **CONTEXT).worksheet_id
    before = len(api.calls)

    class SlowLock:
        released = False

        def acquire(self, timeout):
            assert timeout == 90
            clock.sleep(timeout)
            return True

        def release(self):
            self.released = True

    lock = SlowLock()
    monkeypatch.setattr(bigchat_store, "_WRITES", lock)
    with pytest.raises(BigchatStorageError):
        store.register(sid, "U_A", VALUES, **CONTEXT)
    assert len(api.calls) == before
    assert lock.released


def test_nested_get_sheet_does_not_reset_the_creation_deadline(clock, monkeypatch):
    api = SheetsAPI()
    store = BigchatStore(api)
    store.create("event", **CONTEXT)
    original = api.sheets_request
    remaining = []

    def slow(method, suffix, body=None):
        remaining.append(sheets_retry.remaining_seconds())
        if suffix == "?fields=sheets.properties":
            assert remaining[-1] == 1
            clock.sleep(1)
            raise Timeout("nested read exhausted the original budget")
        clock.sleep(44.5)
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", slow)
    with pytest.raises(BigchatStorageError):
        store.create("event", **CONTEXT)
    assert remaining == [90, 45.5, 1]
    assert clock.now == 90


def sdk_client(auth=None):
    client = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    client.spreadsheet_id = "test-document"
    client.gs_client = gspread.Client(
        auth=auth or AnonymousCredentials(), http_client=SheetsHTTPClient
    )
    client.gs_client.set_timeout((5, 20))
    return client


def ok_response():
    response = Response()
    response.status_code = 200
    response._content = b"{}"
    return response


def test_installed_sdk_receives_only_the_remaining_network_timeout(clock, monkeypatch):
    sent = []
    monkeypatch.setattr(
        HTTPAdapter,
        "send",
        lambda self, request, **kw: sent.append(kw["timeout"]) or ok_response(),
    )
    client = sdk_client()
    with pytest.raises(sheets_retry.OperationTimeout), sheets_retry.operation_budget():
        clock.sleep(88)
        assert client.sheets_request("get", "?fields=sheets.properties") == {}
        assert sent[0].total == 2
        assert sent[0].connect_timeout == 2
        clock.sleep(2)
        client.sheets_request("get", "?fields=sheets.properties")
    assert len(sent) == 1


def test_a_response_that_arrives_at_the_deadline_is_still_returned(clock, monkeypatch):
    sent = []

    def send(self, request, **kwargs):
        sent.append(kwargs["timeout"].total)
        clock.sleep(kwargs["timeout"].total)  # the reply lands at the deadline
        return ok_response()

    monkeypatch.setattr(HTTPAdapter, "send", send)
    client = sdk_client()
    with sheets_retry.operation_budget():
        assert client.sheets_request("get", "?fields=sheets.properties") == {}
        with pytest.raises(sheets_retry.OperationTimeout):
            client.sheets_request("get", "?fields=sheets.properties")
    assert sent == [90]


def test_legacy_read_metadata_and_values_retries_share_one_deadline(clock, monkeypatch):
    sent = []
    metadata = {
        "spreadsheetId": "test-document",
        "properties": {"title": "Test"},
        "sheets": [
            {
                "properties": {
                    "sheetId": 123,
                    "title": "Test",
                    "gridProperties": {"rowCount": 100, "columnCount": 4},
                }
            }
        ],
    }

    def send(self, request, **kwargs):
        left = kwargs["timeout"].total
        sent.append((request.url, left))
        clock.sleep(min(20, left))
        if left <= 20:
            raise Timeout("request exhausted the remaining deadline")
        response = ok_response()
        if "/values/" in request.url:
            response.status_code = 503
            response._content = b'{"error":{"code":503,"message":"unavailable"}}'
        else:
            response._content = json.dumps(metadata).encode()
        return response

    monkeypatch.setattr(HTTPAdapter, "send", send)
    with pytest.raises(sheets_retry.OperationTimeout):
        sdk_client().get_values(123)
    assert [left for _, left in sent] == [90, 70, 50, 29, 9]
    assert sum("/values/" in url for url, _ in sent) == 1
    assert clock.now == 90
    assert sheets_retry.remaining_seconds() is None


@pytest.mark.parametrize("auth_seconds", [89, 91])
def test_credential_refresh_and_sheets_send_share_the_deadline(
    clock, monkeypatch, auth_seconds
):
    class Credentials(AnonymousCredentials):
        def before_request(self, request, method, url, headers):
            request("https://oauth.example.test/token", method="POST")

    sent = []

    def send(self, request, **kwargs):
        sent.append((request.url, kwargs["timeout"].total))
        if request.url.endswith("/token"):
            clock.sleep(auth_seconds)
        return ok_response()

    monkeypatch.setattr(HTTPAdapter, "send", send)
    client = sdk_client(Credentials())
    if auth_seconds > 90:
        # The late token reply is kept, but the Sheets request is never sent.
        with (
            pytest.raises(sheets_retry.OperationTimeout),
            sheets_retry.operation_budget(),
        ):
            client.sheets_request("get", "?fields=sheets.properties")
        assert len(sent) == 1
    else:
        with sheets_retry.operation_budget():
            assert client.sheets_request("get", "?fields=sheets.properties") == {}
        assert [remaining for _, remaining in sent] == [90, 1]
