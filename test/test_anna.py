"""옮긴 main 진입점의 등록·ack·오류 안내·스케줄 설정을 검증한다."""

import json
from unittest.mock import MagicMock

import pytest
from flask import Response

import slack_controller
from features.bigchat.calendar import KST
from features.bigchat.handlers.create_bigchat_modal import (
    CREATE_BIGCHAT_SHORTCUT_ID,
    CREATE_BIGCHAT_VIEW_ID,
)
from shared import error_boundary
from test.fixtures.anna import load_anna
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_message_shortcut_body,
    create_sample_reaction_added_event,
    create_sample_view_submission_body,
)


@pytest.mark.parametrize("reminders", [False, True])
@pytest.mark.parametrize("digest", [False, True])
def test_entrypoint_keeps_main_handlers_and_scheduler_settings(
    monkeypatch, reminders, digest
):
    module, bolt, scheduler = load_anna(monkeypatch, reminders=reminders, digest=digest)
    assert {selector for kind, selector in bolt.handlers if kind == "event"} == {
        "reaction_added",
        "reaction_removed",
        "app_mention",
        "channel_created",
        "message",
    }
    assert ("shortcut", CREATE_BIGCHAT_SHORTCUT_ID) in bolt.handlers
    assert ("view", CREATE_BIGCHAT_VIEW_ID) in bolt.handlers
    actions = [selector for kind, selector in bolt.handlers if kind == "action"]
    assert len(actions) == 1 and actions[0].match("calendar_gcal")
    expected = [
        (enabled, job, hour, name)
        for enabled, job, hour, name in (
            (reminders, module.remind_bigchat, 18, "bigchat-reminder"),
            (digest, module.post_daily_digest, 10, "daily-digest"),
        )
        if enabled
    ]
    assert scheduler.call_count == len(expected)
    assert scheduler.return_value.start.call_count == len(expected)
    for call, (_, job, hour, name) in zip(scheduler.call_args_list, expected):
        assert call.kwargs == dict(job=job, hour=hour, minute=0, tz=KST, name=name)


def test_health_and_slack_http_routes(monkeypatch):
    module, _, _ = load_anna(monkeypatch)
    client = module.flask_app.test_client()
    assert client.get("/health").json == {"status": "ok"}
    assert client.get("/slack/events").status_code == 405
    handler = MagicMock()
    handler.handle.return_value = Response("accepted", status=202)
    monkeypatch.setattr(module, "slack_request_handler", handler)
    response = client.post("/slack/events", json={"type": "url_verification"})
    assert response.status_code == 202 and response.text == "accepted"
    handler.handle.assert_called_once()


@pytest.mark.parametrize(
    "event_type,function",
    [("app_mention", "mention_response"), ("message", "subin_like_response")],
)
@pytest.mark.parametrize(
    "edited", [{"edited": {"ts": "2"}}, {"subtype": "message_changed"}]
)
def test_edited_events_are_acked_without_running_commands(
    monkeypatch, event_type, function, edited
):
    module, bolt, _ = load_anna(monkeypatch)
    dispatch = MagicMock()
    monkeypatch.setattr(module, function, dispatch)
    ack = MagicMock()
    bolt.handlers["event", event_type](
        ack=ack, event={"ts": "1", **edited}, say=MagicMock(), client=MagicMock()
    )
    ack.assert_called_once_with()
    dispatch.assert_not_called()


@pytest.mark.parametrize(
    "event_type,function",
    [
        ("reaction_added", "join_bigchat"),
        ("reaction_removed", "abandon_bigchat"),
        ("app_mention", "mention_response"),
        ("channel_created", "announce_new_channel_created"),
        ("message", "subin_like_response"),
    ],
)
def test_events_ack_before_forwarding_the_original_payload(
    monkeypatch, event_type, function
):
    module, bolt, _ = load_anna(monkeypatch)
    trace = MagicMock()
    monkeypatch.setattr(module, function, trace.dispatch)
    event = (
        create_sample_reaction_added_event("gogo")
        if event_type.startswith("reaction")
        else create_sample_app_mention_event("<@U01BN035Y6L> help")
    )
    say, client = MagicMock(), MagicMock()
    bolt.handlers["event", event_type](
        ack=trace.ack, event=event, say=say, client=client
    )
    assert [call[0] for call in trace.mock_calls] == ["ack", "dispatch"]
    trace.dispatch.assert_called_once_with(event=event, say=say, client=client)


@pytest.mark.parametrize("thread_ts", [None, "1688800000.000001"])
def test_shortcut_keeps_main_normalization(monkeypatch, thread_ts):
    module, bolt, _ = load_anna(monkeypatch)
    dispatch = MagicMock()
    monkeypatch.setattr(module, "open_create_bigchat_modal", dispatch)
    body = create_sample_message_shortcut_body(thread_ts=thread_ts)
    say, client, ack = MagicMock(), MagicMock(), MagicMock()
    bolt.handlers["shortcut", CREATE_BIGCHAT_SHORTCUT_ID](
        ack=ack, body=body, say=say, client=client
    )
    event = dispatch.call_args.kwargs["event"]
    assert event["channel"] == body["channel"]["id"]
    assert event["ts"] == (thread_ts or body["message"]["ts"])
    assert event["user"] == body["user"]["id"]
    ack.assert_called_once_with()


@pytest.mark.parametrize("kind", ["modal", "shortcut"])
def test_interaction_failures_keep_main_thread_notice(monkeypatch, kind):
    _, bolt, _ = load_anna(monkeypatch)
    monkeypatch.setattr(error_boundary, "ADMIN_CHANNEL", "C_ADMIN")
    monkeypatch.setattr(slack_controller, "GoogleSpreadsheetClient", MagicMock())
    monkeypatch.setattr(slack_controller, "_get_member_manager", MagicMock())
    if kind == "modal":
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )
        metadata = json.loads(body["view"]["private_metadata"])
        channel, ts = metadata["channel"], metadata["thread_ts"]
        handler = MagicMock()
        handler.return_value.run.side_effect = RuntimeError("시트 생성 실패")
        monkeypatch.setattr(slack_controller, "SubmitCreateBigchatModal", handler)
        callback = bolt.handlers["view", CREATE_BIGCHAT_VIEW_ID]
    else:
        body = create_sample_message_shortcut_body()
        channel, ts = body["channel"]["id"], body["message"]["ts"]
        handler = MagicMock()
        handler.return_value.run.side_effect = RuntimeError("모달 열기 실패")
        monkeypatch.setattr(slack_controller, "OpenCreateBigchatModal", handler)
        callback = bolt.handlers["shortcut", CREATE_BIGCHAT_SHORTCUT_ID]
    say = MagicMock()
    callback(ack=MagicMock(), body=body, say=say, client=MagicMock())
    assert say.call_count == 2
    assert say.call_args_list[0].kwargs["channel"] == "C_ADMIN"
    assert say.call_args.kwargs["channel"] == channel
    assert say.call_args.kwargs["thread_ts"] == ts
    assert "요청이 정상적으로 처리되지 않았어" in say.call_args.kwargs["text"]


def test_calendar_button_is_acked_without_other_actions(monkeypatch):
    _, bolt, _ = load_anna(monkeypatch)
    callback = next(
        handler for (kind, _), handler in bolt.handlers.items() if kind == "action"
    )
    ack = MagicMock()
    callback(ack=ack)
    ack.assert_called_once_with()
