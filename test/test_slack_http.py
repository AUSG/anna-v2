"""실제 Bolt 어댑터와 Flask 라우트 연결을 외부 API 없이 확인한다."""

import hashlib
import hmac
import json
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest
from slack_bolt import App
from slack_bolt.authorization import AuthorizeResult
from slack_sdk import WebClient
from slack_sdk.web import SlackResponse

from app import create_app
from config.env_config import envs
from integrations.slack import SlackClient
from shared.slack_middleware import LoadingEmoji
from test.fixtures.runtime import fake_dependencies
from test.fixtures.slack_events import (
    create_sample_member,
    create_sample_reaction_added_event,
)

WORKSHEET_ID = 161837744


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
def test_slack_url_verification_uses_the_existing_signed_endpoint(valid_signature):
    secret = "test-signing-secret"
    bolt = App(
        token="xoxb-test", signing_secret=secret, token_verification_enabled=False
    )
    dependencies = fake_dependencies()
    client = create_app(dependencies, bolt_app=bolt).test_client()
    response = post_signed_request(
        client,
        {"type": "url_verification", "challenge": "test-challenge"},
        secret,
        valid_signature=valid_signature,
    )
    if valid_signature:
        assert response.status_code == 200
        assert response.json == {"challenge": "test-challenge"}
    else:
        assert response.status_code == 401
    assert dependencies.mock_calls == []


@pytest.fixture
def registration_runtime():
    dependencies = fake_dependencies()
    dependencies.envs.SLACK_BOT_TOKEN = "xoxb-test"
    dependencies.envs.PUBLIC_BASE_URL = "https://injected.anna.test"
    dependencies.SlackClient = SlackClient
    dependencies.create_web_client.side_effect = lambda: WebClient(
        token=dependencies.envs.SLACK_BOT_TOKEN
    )
    dependencies._loading_emoji.side_effect = lambda slack_client, event: LoadingEmoji(
        slack_client, event["item"]["channel"], event["item"]["ts"]
    )
    dependencies._get_member_manager.return_value.find.return_value = (
        create_sample_member()
    )
    worksheet = dependencies.GoogleSpreadsheetClient.return_value
    worksheet.append_row_if_absent.return_value = True
    worksheet.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
    event = create_sample_reaction_added_event(dependencies.envs.JOIN_BIGCHAT_EMOJI)
    responses = {
        "conversations.replies": {
            "messages": [
                {
                    "ts": event["item"]["ts"],
                    "user": event["item_user"],
                    "text": (
                        "행사 소개글\n<https://docs.google.com/spreadsheets/d/"
                        f"test-sheet/edit#gid={WORKSHEET_ID}|신청 시트>"
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
            bot_user_id=dependencies.envs.ANNA_ID,
            bot_token=dependencies.envs.SLACK_BOT_TOKEN,
        )

    with patch.object(WebClient, "api_call", autospec=True, side_effect=respond) as api:
        bolt = App(
            signing_secret=dependencies.envs.SLACK_SIGNING_SECRET,
            authorize=authorize,
            process_before_response=True,
        )
        client = create_app(dependencies, bolt_app=bolt).test_client()
        yield client, dependencies, event, api


@pytest.mark.parametrize("global_secret", ["global-secret", ""])
@pytest.mark.parametrize("enabled", [True, False])
def test_registered_calendar_link_uses_injected_settings(
    registration_runtime, monkeypatch, global_secret, enabled
):
    client, dependencies, event, api = registration_runtime
    monkeypatch.setattr(envs, "ICS_TOKEN_SECRET", global_secret)
    monkeypatch.setattr(envs, "PUBLIC_BASE_URL", "https://global.anna.test")
    dependencies.envs.ICS_TOKEN_SECRET = "injected-secret" if enabled else ""

    response = post_signed_request(
        client,
        {
            "type": "event_callback",
            "team_id": "T_TEST",
            "event_id": "Ev_TEST",
            "event": event,
        },
        dependencies.envs.SLACK_SIGNING_SECRET,
    )

    assert response.status_code == 200
    dependencies._get_member_manager.return_value.find.assert_called_once_with(
        event["user"]
    )
    dependencies.GoogleSpreadsheetClient.return_value.append_row_if_absent.assert_called_once_with(
        WORKSHEET_ID, ["김동주", "school_name_or_company_name", "email", "phone"]
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
        button["action_id"]: button for button in ephemeral[0]["blocks"][1]["elements"]
    }
    assert "calendar_gcal" in buttons

    if not enabled:
        assert "calendar_ics" not in buttons
        assert client.get(f"/bigchat/{WORKSHEET_ID}/event.ics").status_code == 404
        assert dependencies.GoogleSpreadsheetClient.call_count == 1
        dependencies.create_web_client.assert_not_called()
        return

    url = urlsplit(buttons["calendar_ics"]["url"])
    assert url.scheme == "https"
    assert url.netloc == "injected.anna.test"
    assert url.path == f"/bigchat/{WORKSHEET_ID}/event.ics"
    parameters = {key: values[0] for key, values in parse_qs(url.query).items()}
    assert parameters["channel"] == event["item"]["channel"]
    assert parameters["ts"] == event["item"]["ts"]
    payload = f"{WORKSHEET_ID}:{event['item']['channel']}:{event['item']['ts']}"
    expected_token = hmac.new(
        dependencies.envs.ICS_TOKEN_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    assert parameters["token"] == expected_token
    downloaded = client.get(url.path, query_string=parameters)
    assert downloaded.status_code == 200
    assert downloaded.mimetype == "text/calendar"
    assert "SUMMARY:AI 밋업" in downloaded.text

    sheets_calls = dependencies.GoogleSpreadsheetClient.call_count
    web_clients = dependencies.create_web_client.call_count
    api_calls = api.call_count
    for changed in (
        {"token": "invalid-token"},
        {"channel": "C_OTHER"},
        {"ts": "changed"},
    ):
        assert (
            client.get(url.path, query_string={**parameters, **changed}).status_code
            == 403
        )
    assert dependencies.GoogleSpreadsheetClient.call_count == sheets_calls
    assert dependencies.create_web_client.call_count == web_clients
    assert api.call_count == api_calls
