"""배포·로컬 실행, 앱 등록과 스케줄 시작을 검증한다."""

import runpy
from unittest.mock import MagicMock

import pytest
from flask import Response

import app
from features.bigchat import jobs as bigchat_jobs, slack as bigchat_slack
from features.bigchat.presentation.modals import (
    CREATE_BIGCHAT_SHORTCUT_ID,
    CREATE_BIGCHAT_VIEW_ID,
)
from features.community import jobs as community_jobs, slack as community_slack
from shared.time import KST
from test.fixtures.runtime import FakeBoltApp, fake_dependencies


@pytest.fixture
def runtime():
    dependencies = fake_dependencies()
    bolt_app = FakeBoltApp()
    flask_app = app.create_app(dependencies, bolt_app=bolt_app)
    return flask_app, bolt_app, dependencies


def test_factory_registers_all_slack_entrypoints_without_constructing_clients(runtime):
    flask_app, bolt_app, dependencies = runtime
    assert {name for (kind, name) in bolt_app.handlers if kind == "event"} == {
        "reaction_added",
        "reaction_removed",
        "message",
        "channel_created",
        "app_mention",
    }
    assert ("shortcut", CREATE_BIGCHAT_SHORTCUT_ID) in bolt_app.handlers
    assert ("view", CREATE_BIGCHAT_VIEW_ID) in bolt_app.handlers
    actions = [selector for kind, selector in bolt_app.handlers if kind == "action"]
    assert len(actions) == 1 and actions[0].match("calendar_gcal")
    assert flask_app.extensions["slack_app"] is bolt_app
    assert dependencies.mock_calls == []


def test_health_response_and_http_routes(runtime):
    flask_app, _, dependencies = runtime
    client = flask_app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    rules = {rule.rule: rule.methods for rule in flask_app.url_map.iter_rules()}
    assert "POST" in rules["/slack/events"]
    assert "GET" in rules["/bigchat/<int:worksheet_id>/event.ics"]
    assert client.get("/slack/events").status_code == 405
    assert dependencies.mock_calls == []


def test_webhook_is_forwarded_to_bolt(monkeypatch):
    request_handler = MagicMock()
    request_handler.handle.return_value = Response("accepted", status=202)
    factory = MagicMock(return_value=request_handler)
    monkeypatch.setattr(app, "SlackRequestHandler", factory)
    bolt_app = FakeBoltApp()
    flask_app = app.create_app(fake_dependencies(), bolt_app=bolt_app)
    response = flask_app.test_client().post(
        "/slack/events", json={"type": "url_verification"}
    )
    assert response.status_code == 202 and response.text == "accepted"
    factory.assert_called_once_with(bolt_app)
    request_handler.handle.assert_called_once()


@pytest.mark.parametrize(
    "edited", [{"edited": {"ts": "2"}}, {"subtype": "message_changed"}]
)
@pytest.mark.parametrize("event_type", ["app_mention", "message"])
def test_edited_messages_are_acked_without_dispatch(
    runtime, monkeypatch, edited, event_type
):
    _, bolt_app, _ = runtime
    dispatch = MagicMock()
    if event_type == "app_mention":
        monkeypatch.setattr(app, "mention_response", dispatch)
    else:
        monkeypatch.setattr(community_slack, "subin_like_response", dispatch)
    ack = MagicMock()
    bolt_app.handlers["event", event_type](
        ack=ack,
        event={"ts": "1", **edited},
        say=MagicMock(),
        client=MagicMock(),
    )
    ack.assert_called_once_with()
    dispatch.assert_not_called()


@pytest.mark.parametrize(
    ("event_type", "function"),
    [("reaction_added", "join_bigchat"), ("reaction_removed", "abandon_bigchat")],
)
def test_reaction_handlers_ack_before_dispatch(
    runtime, monkeypatch, event_type, function
):
    _, bolt_app, dependencies = runtime
    trace = MagicMock()
    monkeypatch.setattr(bigchat_slack, function, trace.dispatch)
    event, say, client = {}, MagicMock(), MagicMock()
    bolt_app.handlers["event", event_type](
        ack=trace.ack, event=event, say=say, client=client
    )
    assert [call[0] for call in trace.mock_calls] == ["ack", "dispatch"]
    trace.dispatch.assert_called_once_with(
        event=event, say=say, client=client, dependencies=dependencies
    )


@pytest.mark.parametrize("bigchat_enabled", [False, True])
@pytest.mark.parametrize("digest_enabled", [False, True])
def test_schedulers_start_only_when_explicitly_requested(
    monkeypatch, bigchat_enabled, digest_enabled
):
    dependencies = fake_dependencies()
    dependencies.envs.BIGCHAT_REMINDER_ENABLED = bigchat_enabled
    dependencies.envs.DAILY_DIGEST_ENABLED = digest_enabled
    reminders, digests = MagicMock(), MagicMock()
    monkeypatch.setattr(bigchat_jobs, "DailyScheduler", reminders)
    monkeypatch.setattr(community_jobs, "DailyScheduler", digests)
    app.create_app(dependencies, bolt_app=FakeBoltApp())
    reminders.assert_not_called()
    digests.assert_not_called()

    app.start_schedulers(dependencies)
    for enabled, factory, hour, name in (
        (bigchat_enabled, reminders, 18, "bigchat-reminder"),
        (digest_enabled, digests, 10, "daily-digest"),
    ):
        assert factory.call_count == int(enabled)
        if enabled:
            assert factory.call_args.kwargs["hour"] == hour
            assert factory.call_args.kwargs["minute"] == 0
            assert factory.call_args.kwargs["tz"] is KST
            assert factory.call_args.kwargs["name"] == name
            assert factory.call_args.kwargs["job"].args == (dependencies,)
            factory.return_value.start.assert_called_once_with()
    assert dependencies.mock_calls == []


@pytest.mark.parametrize("module_name", ["anna_boot_test", "__main__"])
def test_gunicorn_and_local_entrypoints_initialize_the_app(monkeypatch, module_name):
    flask_app = MagicMock()
    bolt_app = flask_app.extensions["slack_app"]
    factory = MagicMock(return_value=flask_app)
    schedulers = MagicMock()
    monkeypatch.setattr(app, "create_app", factory)
    monkeypatch.setattr(app, "start_schedulers", schedulers)
    monkeypatch.setattr("config.log_config.init_logger", MagicMock())

    namespace = runpy.run_module("anna", run_name=module_name)
    assert namespace["flask_app"] is flask_app
    assert namespace["app"] is bolt_app
    factory.assert_called_once_with()
    schedulers.assert_called_once_with()
    if module_name == "__main__":
        flask_app.run.assert_called_once_with(host="0.0.0.0", port=8080)
    else:
        flask_app.run.assert_not_called()
