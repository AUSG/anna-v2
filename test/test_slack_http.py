"""Slack HTTP 요청과 캘린더 다운로드를 외부 API 없이 검증한다."""

import hashlib
import hmac
import json
import time
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from slack_bolt import App
from slack_bolt.authorization import AuthorizeResult
from slack_sdk import WebClient
from slack_sdk.web import SlackResponse

from features.bigchat.calendar import calendar_payload, calendar_token
from features.members.services.directory import Member
from test.fixtures.anna import load_anna
from test.fixtures.slack_events import create_sample_reaction_added_event

WORKSHEET_ID = 161837744
CHANNEL = "C_BIGCHAT"
TS = "1688801145.307229"
SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"


def query(secret="testsecret", *, channel=CHANNEL, ts=TS):
    return {
        "channel": channel,
        "ts": ts,
        "token": calendar_token(secret, calendar_payload(WORKSHEET_ID, channel, ts)),
    }


@pytest.fixture
def calendar_app(monkeypatch):
    module, _, _ = load_anna(monkeypatch)
    sheets = MagicMock()
    sheets.return_value.get_worksheet_title.return_value = SHEET_NAME
    web = MagicMock()
    web.return_value.chat_getPermalink.return_value = {
        "permalink": "https://slack.test/intro"
    }
    web.return_value.conversations_replies.return_value = {
        "messages": [{"text": "행사 소개글\n둘째 줄"}]
    }
    monkeypatch.setattr(module.services, "sheets", sheets)
    monkeypatch.setattr(module.services, "web_client", web)
    return module, module.flask_app.test_client(), sheets, web


def test_download_returns_calendar_with_description(calendar_app):
    _, client, sheets, web = calendar_app
    response = client.get(f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query())
    assert response.status_code == 200
    assert response.mimetype == "text/calendar"
    assert response.headers["Content-Disposition"] == 'attachment; filename="event.ics"'
    content = response.text.replace("\r\n ", "")
    assert "UID:bigchat-161837744@ausg-anna\r\n" in content
    assert "DTSTART:20260820T100000Z\r\n" in content
    assert "SUMMARY:AI 밋업\r\n" in content
    assert (
        "DESCRIPTION:슬랙에서 소개글 보기: https://slack.test/intro\\n\\n행사 소개글\\n둘째 줄\r\n"
        in content
    )
    sheets.return_value.get_worksheet_title.assert_called_once_with(WORKSHEET_ID)
    web.return_value.conversations_replies.assert_called_once_with(
        channel=CHANNEL, ts=TS, limit=1
    )


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_disabled_download_does_not_construct_clients(
    calendar_app, monkeypatch, method
):
    module, client, sheets, web = calendar_app
    monkeypatch.setattr(module.settings, "ICS_TOKEN_SECRET", "")
    assert (
        client.open(
            f"/bigchat/{WORKSHEET_ID}/event.ics", method=method, query_string=query()
        ).status_code
        == 404
    )
    sheets.assert_not_called()
    web.assert_not_called()


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        query("wrong-secret"),
        {**query(), "channel": "C_OTHER"},
        {**query(), "ts": "changed"},
    ],
)
def test_invalid_token_is_rejected_before_sheets_initialization(
    calendar_app, parameters
):
    _, client, sheets, web = calendar_app
    sheets.side_effect = RuntimeError("자격증명 초기화 실패")
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=parameters
        ).status_code
        == 403
    )
    sheets.assert_not_called()
    web.assert_not_called()


@pytest.mark.parametrize("failure", ["constructor", "read", "missing", "invalid_title"])
def test_calendar_lookup_failures_return_404(calendar_app, failure):
    _, client, sheets, web = calendar_app
    if failure == "constructor":
        sheets.side_effect = RuntimeError("자격증명 초기화 실패")
    elif failure == "read":
        sheets.return_value.get_worksheet_title.side_effect = RuntimeError(
            "시트 조회 실패"
        )
    else:
        sheets.return_value.get_worksheet_title.return_value = (
            None if failure == "missing" else "구형식 시트"
        )
    assert (
        client.get(
            f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query()
        ).status_code
        == 404
    )
    web.assert_not_called()


@pytest.mark.parametrize("method", ["chat_getPermalink", "conversations_replies"])
def test_optional_slack_lookup_failure_does_not_prevent_download(calendar_app, method):
    _, client, _, web = calendar_app
    getattr(web.return_value, method).side_effect = RuntimeError("Slack unavailable")
    response = client.get(f"/bigchat/{WORKSHEET_ID}/event.ics", query_string=query())
    assert response.status_code == 200
    assert "BEGIN:VCALENDAR" in response.text


def post_signed_request(client, payload, secret, *, valid_signature=True):
    body = json.dumps(payload)
    timestamp = str(int(time.time()))
    signature = (
        "v0="
        + hmac.new(
            secret.encode(), f"v0:{timestamp}:{body}".encode(), hashlib.sha256
        ).hexdigest()
    )
    return client.post(
        "/slack/events",
        data=body,
        content_type="application/json",
        headers={
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": signature if valid_signature else "v0=wrong",
        },
    )


@pytest.mark.parametrize("valid_signature", [True, False])
def test_real_bolt_url_verification(monkeypatch, valid_signature):
    secret = "test-signing-secret"
    bolt = App(
        token="xoxb-test", signing_secret=secret, token_verification_enabled=False
    )
    module, _, _ = load_anna(monkeypatch, bolt_app=bolt)
    response = post_signed_request(
        module.flask_app.test_client(),
        {"type": "url_verification", "challenge": "test-challenge"},
        secret,
        valid_signature=valid_signature,
    )
    assert response.status_code == (200 if valid_signature else 401)
    if valid_signature:
        assert response.json == {"challenge": "test-challenge"}


@pytest.mark.parametrize("ics_enabled", [True, False])
def test_real_bolt_registration_calendar_roundtrip(monkeypatch, ics_enabled):
    secret = "test-signing-secret"
    event = create_sample_reaction_added_event("gogo")
    responses = {
        "conversations.replies": {
            "messages": [
                {
                    "ts": event["item"]["ts"],
                    "user": event["item_user"],
                    "text": (
                        "행사 소개글\n"
                        f"<https://docs.google.com/spreadsheets/d/test-sheet/edit#gid={WORKSHEET_ID}|신청 시트>"
                    ),
                }
            ]
        },
        "chat.getPermalink": {"permalink": "https://slack.test/intro"},
        "chat.postMessage": {},
        "chat.postEphemeral": {},
        "reactions.add": {},
        "reactions.remove": {},
    }

    def respond(web_client, api_method, **kwargs):
        assert api_method in responses, f"Unexpected Slack API: {api_method}"
        return SlackResponse(
            client=web_client,
            http_verb="POST",
            api_url=f"https://slack.test/api/{api_method}",
            req_args=kwargs,
            data={"ok": True, **responses[api_method]},
            headers={},
            status_code=200,
        )

    def authorize(enterprise_id, team_id):
        return AuthorizeResult(
            enterprise_id=enterprise_id,
            team_id=team_id,
            bot_user_id="U01BN035Y6L",
            bot_token="xoxb-test",
        )

    with patch.object(WebClient, "api_call", autospec=True, side_effect=respond) as api:
        bolt = App(
            signing_secret=secret, authorize=authorize, process_before_response=True
        )
        module, _, _ = load_anna(monkeypatch, bolt_app=bolt)
        monkeypatch.setattr(
            module.settings, "ICS_TOKEN_SECRET", "testsecret" if ics_enabled else ""
        )
        members, sheets = MagicMock(), MagicMock()
        members.find.return_value = Member(
            kor_name="김철수",
            eng_name="Kim",
            email="me@example.com",
            phone="010-1234-5678",
            school_name_or_company_name="AUSG",
        )
        sheets.find_bigchat.return_value = WORKSHEET_ID
        sheets.register_bigchat.return_value = True
        sheets.get_worksheet_title.return_value = SHEET_NAME
        monkeypatch.setattr(module.services, "members", lambda: members)
        monkeypatch.setattr(module.services, "sheets", lambda: sheets)
        client = module.flask_app.test_client()
        response = post_signed_request(
            client,
            {
                "type": "event_callback",
                "team_id": "T_TEST",
                "event_id": "Ev_TEST",
                "event": event,
            },
            secret,
        )
        assert response.status_code == 200
        sheets.register_bigchat.assert_called_once_with(
            WORKSHEET_ID,
            event["user"],
            ["김철수", "AUSG", "me@example.com", "010-1234-5678"],
            channel=event["item"]["channel"],
            thread_ts=event["item"]["ts"],
        )
        ephemeral = [
            call.kwargs["json"]
            for call in api.call_args_list
            if call.args[1] == "chat.postEphemeral"
        ]
        assert len(ephemeral) == 1
        assert ephemeral[0]["channel"] == event["item"]["channel"]
        assert ephemeral[0]["user"] == event["user"]
        assert ephemeral[0]["thread_ts"] == event["item"]["ts"]
        buttons = {
            button["action_id"]: button
            for button in ephemeral[0]["blocks"][1]["elements"]
        }
        assert "calendar_gcal" in buttons
        if not ics_enabled:
            assert "calendar_ics" not in buttons
            assert client.get(f"/bigchat/{WORKSHEET_ID}/event.ics").status_code == 404
            return
        url = urlsplit(buttons["calendar_ics"]["url"])
        assert url.netloc == "anna.test"
        parameters = {key: values[0] for key, values in parse_qs(url.query).items()}
        download = client.get(url.path, query_string=parameters)
        assert download.status_code == 200
        assert "SUMMARY:AI 밋업" in download.text
        before = api.call_count
        assert (
            client.get(
                url.path, query_string={**parameters, "token": "wrong"}
            ).status_code
            == 403
        )
        assert api.call_count == before
