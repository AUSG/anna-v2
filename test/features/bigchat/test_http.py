from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask

from features.bigchat.http import create_blueprint
from features.bigchat.models import parse_sheet_name
from features.bigchat.services.calendar import (
    calendar_links,
    calendar_payload,
    calendar_token,
)
from shared.slack_models import Message
from test.fixtures.runtime import fake_runtime

WORKSHEET_ID = 161837744
CHANNEL = "C_BIGCHAT"
TS = "1688801145.307229"
SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"


@pytest.fixture
def runtime():
    runtime = fake_runtime()
    runtime.sheets().get_worksheet_title.return_value = SHEET_NAME
    runtime.slack.get_permalink.return_value = "https://slack.test/intro"
    runtime.slack.get_thread.return_value = [
        Message(
            ts=TS,
            thread_ts=TS,
            channel=CHANNEL,
            user="U01BN035Y6L",
            text="행사 소개글\n둘째 줄",
        ),
    ]
    app = Flask(__name__)
    app.register_blueprint(create_blueprint(runtime))
    return app.test_client(), runtime


def query(secret="testsecret", *, channel=CHANNEL, ts=TS):
    return {
        "channel": channel,
        "ts": ts,
        "token": calendar_token(secret, calendar_payload(WORKSHEET_ID, channel, ts)),
    }


def test_download_keeps_ics_content_headers_and_live_description(runtime):
    client, runtime = runtime
    response = client.get(f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query())
    assert response.status_code == 200
    assert response.mimetype == "text/calendar"
    assert response.headers["Content-Disposition"] == 'attachment; filename="event.ics"'
    content = response.data.decode().replace("\r\n ", "")
    assert "UID:bigchat-161837744@ausg-anna\r\n" in content
    assert "DTSTART:20260820T100000Z\r\n" in content
    assert "SUMMARY:AI 밋업\r\n" in content
    assert (
        "DESCRIPTION:슬랙에서 소개글 보기: https://slack.test/intro\\n\\n행사 소개글\\n둘째 줄\r\n"
        in content
    )
    # 소개글은 클릭 시점에 Slack 에서 읽는다
    runtime.sheets().get_worksheet_title.assert_called_once_with(WORKSHEET_ID)
    runtime.slack.get_permalink.assert_called_once_with(CHANNEL, TS)
    runtime.slack.get_thread.assert_called_once_with(CHANNEL, TS)


def test_disabled_download_does_not_touch_sheets_or_slack(runtime):
    client, runtime = runtime
    runtime.settings.ICS_TOKEN_SECRET = ""
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query()
        ).status_code
        == 404
    )
    assert runtime.sheets().mock_calls == []
    assert runtime.slack.mock_calls == []
    assert runtime.web_clients == []


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("raw_query", ["channel=\xff", "token=\x80"])
def test_disabled_download_does_not_parse_malformed_query(runtime, method, raw_query):
    client, runtime = runtime
    runtime.settings.ICS_TOKEN_SECRET = ""

    response = client.open(
        f"/bigchat/{WORKSHEET_ID}/event.ics",
        method=method,
        environ_overrides={"QUERY_STRING": raw_query},
    )

    assert response.status_code == 404
    assert runtime.sheets().mock_calls == []
    assert runtime.slack.mock_calls == []
    assert runtime.web_clients == []


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        query("wrong-secret"),
        {**query(), "channel": "C_OTHER"},
        {**query(), "ts": "changed"},
    ],
)
def test_invalid_or_tampered_token_fails_before_external_lookup(runtime, parameters):
    client, runtime = runtime
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=parameters
        ).status_code
        == 403
    )
    assert runtime.sheets().mock_calls == []
    assert runtime.slack.mock_calls == []


@pytest.mark.parametrize(
    "unavailable", ["read_failure", "invalid_title", "missing_title"]
)
def test_missing_or_invalid_event_is_not_found(runtime, unavailable):
    client, runtime = runtime
    sheets = runtime.sheets()
    if unavailable == "read_failure":
        sheets.get_worksheet_title.side_effect = RuntimeError("read failed")
    else:
        sheets.get_worksheet_title.return_value = (
            "old sheet" if unavailable == "invalid_title" else None
        )
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query()
        ).status_code
        == 404
    )
    assert runtime.slack.mock_calls == []


@pytest.mark.parametrize("failed_method", ["get_permalink", "get_thread"])
def test_optional_slack_read_failure_does_not_prevent_download(runtime, failed_method):
    client, runtime = runtime
    getattr(runtime.slack, failed_method).side_effect = RuntimeError(
        "Slack unavailable"
    )
    response = client.get(f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query())
    assert response.status_code == 200
    assert "BEGIN:VCALENDAR" in response.text


def test_calendar_button_url_roundtrips_through_the_download_endpoint(runtime):
    client, runtime = runtime
    links = calendar_links(
        parse_sheet_name(SHEET_NAME),
        WORKSHEET_ID,
        CHANNEL,
        TS,
        "https://slack.test/intro",
        "소개글",
        public_base_url=runtime.settings.PUBLIC_BASE_URL,
        token_secret=runtime.settings.ICS_TOKEN_SECRET,
    )
    assert links.gcal_url.startswith("https://calendar.google.com/calendar/render?")
    url = urlsplit(links.ics_url)
    assert url.netloc == "anna.test"
    parameters = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert client.get(url.path, query_string=parameters).status_code == 200
