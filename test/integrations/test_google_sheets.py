from types import SimpleNamespace
from unittest.mock import MagicMock

import gspread
import pytest
from google.auth.credentials import AnonymousCredentials
from gspread.exceptions import APIError
from requests import Response

from integrations.google_sheets import GoogleSpreadsheetClient


@pytest.mark.parametrize("gspread6", [False, True])
def test_raw_sheets_transport_uses_the_authenticated_sdk_client(gspread6):
    client = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    client.spreadsheet_id = "configured-sheet"
    request = MagicMock()
    request.return_value.json.return_value = {"ok": True}
    transport = SimpleNamespace(request=request)
    client.gs_client = SimpleNamespace(http_client=transport) if gspread6 else transport
    payload = {"data": []}
    assert client.sheets_request(
        "post", "/values:batchUpdateByDataFilter", payload
    ) == {"ok": True}
    request.assert_called_once_with(
        "post",
        "https://sheets.googleapis.com/v4/spreadsheets/configured-sheet/values:batchUpdateByDataFilter",
        json=payload,
    )


@pytest.mark.parametrize("status", [200, 403])
def test_raw_transport_through_the_real_installed_gspread_sdk(status):
    response = Response()
    response.status_code = status
    response._content = (
        b'{"error":{"code":403,"message":"denied"}}'
        if status == 403
        else b'{"totalUpdatedRows":1}'
    )
    session = MagicMock()
    session.request.return_value = response
    session.post.side_effect = lambda url, **kwargs: session.request(
        "post", url, **kwargs
    )
    client = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    client.spreadsheet_id = "configured-document"
    client.gs_client = gspread.Client(auth=AnonymousCredentials(), session=session)
    client.gs_client.set_timeout((5, 20))
    if status == 403:
        with pytest.raises(APIError):
            client.sheets_request(
                "post", "/values:batchUpdateByDataFilter", {"data": []}
            )
    else:
        assert client.sheets_request(
            "post", "/values:batchUpdateByDataFilter", {"data": []}
        ) == {"totalUpdatedRows": 1}
    assert session.request.call_args.kwargs["timeout"] == (5, 20)
    assert session.request.call_args.kwargs["json"] == {"data": []}


def test_client_uses_injected_settings(monkeypatch):
    from config.env_config import Settings
    from integrations import google_sheets

    settings = Settings(
        _env_file=None,
        FORM_SPREADSHEET_ID="configured-sheet",
        GCP_private_key="line1\\nline2",
    )
    factory = MagicMock()
    monkeypatch.setattr(google_sheets, "service_account_from_dict", factory)
    client = GoogleSpreadsheetClient(settings=settings)
    assert client.spreadsheet_id == "configured-sheet"
    assert client.gs_client is factory.return_value
    assert factory.call_args.args[0]["private_key"] == "line1\nline2"
