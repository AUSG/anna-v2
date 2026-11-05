from unittest.mock import MagicMock

import pytest
from gspread.exceptions import WorksheetNotFound
from requests.exceptions import ChunkedEncodingError, ConnectionError, InvalidURL

from integrations.google_sheets import GoogleSpreadsheetClient
from integrations.sheets_retry import guarded_write, retry_reads
from test.fixtures.sheets import api_error


@pytest.fixture
def delays(monkeypatch):
    observed = []
    monkeypatch.setattr("integrations.sheets_retry.time.sleep", observed.append)
    return observed


def client():
    result = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    result.spreadsheet_id = "configured-document"
    result.gs_client = MagicMock()
    return result


@pytest.mark.parametrize("stage", ["open", "worksheet", "values", "list"])
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 503])
def test_legacy_reads_have_one_attempt_limit_without_nested_amplification(
    stage, status, delays
):
    sheets = client()
    document = sheets.gs_client.open_by_key.return_value
    worksheet = document.get_worksheet_by_id.return_value
    failing = {
        "open": sheets.gs_client.open_by_key,
        "worksheet": document.get_worksheet_by_id,
        "values": worksheet.get_values,
        "list": document.worksheets,
    }[stage]
    error = api_error(status)
    failing.side_effect = error
    with pytest.raises(type(error)) as caught:
        if stage == "list":
            sheets.list_worksheets()
        else:
            sheets.get_values(123)
    assert caught.value is error
    expected_delays = (
        [5, 10, 20, 30] if status == 429 else [1, 2] if status == 503 else []
    )
    assert delays == expected_delays
    assert failing.call_count == len(delays) + 1
    assert sheets.gs_client.open_by_key.call_count == len(delays) + 1


@pytest.mark.parametrize(
    "error",
    [WorksheetNotFound("missing"), ValueError("invalid input"), InvalidURL("bad URL")],
)
def test_missing_sheets_and_programming_errors_are_not_retried(error, delays):
    sheets = client()
    document = sheets.gs_client.open_by_key.return_value
    document.get_worksheet_by_id.side_effect = error
    with pytest.raises(type(error)) as caught:
        sheets.get_worksheet_title(123)
    assert caught.value is error
    assert document.get_worksheet_by_id.call_count == 1
    assert sheets.gs_client.open_by_key.call_count == 1
    assert delays == []


def test_legacy_read_recovers_and_a_new_call_gets_its_own_attempts(delays):
    sheets = client()
    worksheet = (
        sheets.gs_client.open_by_key.return_value.get_worksheet_by_id.return_value
    )
    worksheet.get_values.side_effect = [
        ConnectionError(),
        api_error(503),
        [["ok"]],
        api_error(503),
        [["next"]],
    ]
    assert sheets.get_values(123, "A:D") == [["ok"]]
    assert sheets.get_values(123, "A:D") == [["next"]]
    assert delays == [1, 2, 1]
    assert worksheet.get_values.call_args.args == ("A:D",)


def test_a_read_whose_response_body_was_cut_off_is_retried(delays):
    sheets = client()
    worksheet = (
        sheets.gs_client.open_by_key.return_value.get_worksheet_by_id.return_value
    )
    worksheet.get_values.side_effect = [
        ChunkedEncodingError("Connection broken: IncompleteRead"),
        [["ok"]],
    ]
    assert sheets.get_values(123) == [["ok"]]
    assert delays == [1]


def test_failed_confirmation_is_not_reclassified_as_a_retryable_write(delays):
    send = MagicMock(side_effect=ConnectionError("response lost"))
    error = api_error(503)
    confirm = MagicMock(side_effect=error)
    with pytest.raises(type(error)) as caught:
        guarded_write(send, confirmed=confirm)
    assert caught.value is error
    send.assert_called_once()
    confirm.assert_called_once()
    assert delays == []


def test_only_confirmation_reads_retry_after_an_uncertain_write(delays):
    send = MagicMock(side_effect=ConnectionError("response lost"))
    lookup = MagicMock(side_effect=[api_error(503), api_error(503), True])

    @retry_reads
    def confirm():
        return lookup()

    guarded_write(send, confirmed=confirm)
    send.assert_called_once()
    assert lookup.call_count == 3
    assert delays == [1, 2]


@pytest.mark.parametrize(
    "error", [ValueError("not a transport error"), KeyboardInterrupt()]
)
def test_application_errors_and_interrupts_never_trigger_confirmation(error, delays):
    send, confirm = MagicMock(side_effect=error), MagicMock()
    with pytest.raises(type(error)):
        guarded_write(send, confirmed=confirm)
    send.assert_called_once()
    confirm.assert_not_called()
    assert delays == []


@pytest.mark.parametrize(
    "failure",
    [api_error(503), ChunkedEncodingError("response body cut off")],
    ids=["status-503", "cut-off-body"],
)
def test_confirmed_absence_precedes_each_safe_write_replay(delays, failure):
    order = []
    responses = iter([failure, None])

    def send():
        order.append("write")
        error = next(responses)
        if error:
            raise error

    def confirm():
        order.append("confirm")
        return False

    guarded_write(send, confirmed=confirm)
    assert order == ["write", "confirm", "write"]
    assert delays == [1]
