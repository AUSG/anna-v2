from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest
from flask import Flask

from features.bigchat.http import create_blueprint
from features.bigchat.services.calendar import (
    calendar_payload,
    calendar_token,
    build_registration_calendar_blocks,
)
from test.fixtures.runtime import fake_dependencies

WORKSHEET_ID = 161837744
CHANNEL = "C_BIGCHAT"
TS = "1688801145.307229"


@pytest.fixture
def runtime():
    dependencies = fake_dependencies()
    dependencies.GoogleSpreadsheetClient.return_value.get_worksheet_title.return_value = (
        "AI 밋업 26-08-20 19:00~21:00"
    )
    web_client = dependencies.create_web_client.return_value
    web_client.chat_getPermalink.return_value = {
        "permalink": "https://slack.test/intro"
    }
    web_client.conversations_replies.return_value = {
        "messages": [{"text": "행사 소개글\n둘째 줄"}]
    }
    app = Flask(__name__)
    app.register_blueprint(create_blueprint(dependencies))
    return app.test_client(), dependencies


def query(secret="testsecret", *, channel=CHANNEL, ts=TS):
    return {
        "channel": channel,
        "ts": ts,
        "token": calendar_token(secret, calendar_payload(WORKSHEET_ID, channel, ts)),
    }


def test_download_keeps_ics_content_headers_and_live_description(runtime):
    client, dependencies = runtime
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
    assert dependencies.create_web_client.call_count == 2


def test_disabled_download_does_not_construct_clients(runtime):
    client, dependencies = runtime
    dependencies.envs.ICS_TOKEN_SECRET = ""
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query()
        ).status_code
        == 404
    )
    dependencies.GoogleSpreadsheetClient.assert_not_called()
    dependencies.create_web_client.assert_not_called()


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("raw_query", ["channel=\xff", "token=\x80"])
def test_disabled_download_does_not_parse_malformed_query(runtime, method, raw_query):
    client, dependencies = runtime
    dependencies.envs.ICS_TOKEN_SECRET = ""

    response = client.open(
        f"/bigchat/{WORKSHEET_ID}/event.ics",
        method=method,
        environ_overrides={"QUERY_STRING": raw_query},
    )

    assert response.status_code == 404
    dependencies.GoogleSpreadsheetClient.assert_not_called()
    dependencies.create_web_client.assert_not_called()


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
    client, dependencies = runtime
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=parameters
        ).status_code
        == 403
    )
    dependencies.GoogleSpreadsheetClient.assert_not_called()
    dependencies.create_web_client.assert_not_called()


@pytest.mark.parametrize(
    "unavailable", ["read_failure", "invalid_title", "missing_title"]
)
def test_missing_or_invalid_event_is_not_found(runtime, unavailable):
    client, dependencies = runtime
    worksheet = dependencies.GoogleSpreadsheetClient.return_value
    if unavailable == "read_failure":
        worksheet.get_worksheet_title.side_effect = RuntimeError("read failed")
    else:
        worksheet.get_worksheet_title.return_value = (
            "old sheet" if unavailable == "invalid_title" else None
        )
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query()
        ).status_code
        == 404
    )
    dependencies.create_web_client.assert_not_called()


@pytest.mark.parametrize(
    "failed_method", ["chat_getPermalink", "conversations_replies"]
)
def test_optional_slack_read_failure_does_not_prevent_download(runtime, failed_method):
    client, dependencies = runtime
    getattr(
        dependencies.create_web_client.return_value, failed_method
    ).side_effect = RuntimeError("Slack unavailable")
    response = client.get(f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query())
    assert response.status_code == 200
    assert "BEGIN:VCALENDAR" in response.text


def test_calendar_button_url_roundtrips_through_the_download_endpoint(runtime):
    client, dependencies = runtime
    slack_client = MagicMock()
    slack_client.get_permalink.return_value = "https://slack.test/intro"
    blocks = build_registration_calendar_blocks(
        "등록했어",
        WORKSHEET_ID,
        "소개글",
        CHANNEL,
        TS,
        slack_client,
        dependencies.GoogleSpreadsheetClient.return_value,
        public_base_url=dependencies.envs.PUBLIC_BASE_URL,
        token_secret=dependencies.envs.ICS_TOKEN_SECRET,
    )
    gcal, ics = blocks[1]["elements"]
    assert gcal["url"].startswith("https://calendar.google.com/calendar/render?")
    url = urlsplit(ics["url"])
    assert url.netloc == "anna.test"
    parameters = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert client.get(url.path, query_string=parameters).status_code == 200
