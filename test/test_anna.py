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
from shared.slack_events import ReactionEvent
from shared.time import KST
from test.fixtures.runtime import FakeBoltApp, fake_runtime
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_reaction_added_event,
)

ENTRYPOINT_MODULES = {
    "app_mention": app,
    "reaction_added": bigchat_slack,
    "reaction_removed": bigchat_slack,
    "message": community_slack,
    "channel_created": community_slack,
}


def untouched(runtime):
    """핸들러 등록만으로는 어떤 외부 게이트웨이도 만지지 않아야 한다."""
    return (
        runtime.slack.mock_calls == []
        and runtime.sheets().mock_calls == []
        and runtime.members().mock_calls == []
        and runtime.qa().mock_calls == []
        and runtime.github().mock_calls == []
        and runtime.web_clients == []
    )


@pytest.fixture
def wired():
    runtime = fake_runtime()
    bolt_app = FakeBoltApp()
    flask_app = app.create_app(runtime, bolt_app=bolt_app)
    return flask_app, bolt_app, runtime


def test_factory_registers_all_slack_entrypoints_without_constructing_clients(wired):
    flask_app, bolt_app, runtime = wired
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
    assert untouched(runtime)


def test_health_response_and_http_routes(wired):
    flask_app, _, runtime = wired
    client = flask_app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    rules = {rule.rule: rule.methods for rule in flask_app.url_map.iter_rules()}
    assert "POST" in rules["/slack/events"]
    assert "GET" in rules["/bigchat/<int:worksheet_id>/event.ics"]
    assert client.get("/slack/events").status_code == 405
    assert untouched(runtime)


def test_webhook_is_forwarded_to_bolt(monkeypatch):
    request_handler = MagicMock()
    request_handler.handle.return_value = Response("accepted", status=202)
    factory = MagicMock(return_value=request_handler)
    monkeypatch.setattr(app, "SlackRequestHandler", factory)
    bolt_app = FakeBoltApp()
    flask_app = app.create_app(fake_runtime(), bolt_app=bolt_app)
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
    wired, monkeypatch, edited, event_type
):
    _, bolt_app, runtime = wired
    dispatch = MagicMock()
    if event_type == "app_mention":
        monkeypatch.setattr(app, "mention_response", dispatch)
    else:
        monkeypatch.setattr(community_slack, "subin_like_response", dispatch)
    ack = MagicMock()
    bolt_app.handlers["event", event_type](
        ack=ack, event={"ts": "1", **edited}, client=MagicMock()
    )
    ack.assert_called_once_with()
    dispatch.assert_not_called()
    assert untouched(runtime)


@pytest.mark.parametrize(
    ("event_type", "function"),
    [("reaction_added", "join_bigchat"), ("reaction_removed", "abandon_bigchat")],
)
def test_reaction_handlers_ack_before_dispatch(
    wired, monkeypatch, event_type, function
):
    _, bolt_app, runtime = wired
    trace = MagicMock()
    monkeypatch.setattr(bigchat_slack, function, trace.dispatch)
    event = {**create_sample_reaction_added_event("gogo"), "type": event_type}
    client = MagicMock()
    bolt_app.handlers["event", event_type](ack=trace.ack, event=event, client=client)
    assert [call[0] for call in trace.mock_calls] == ["ack", "dispatch"]
    trace.dispatch.assert_called_once_with(
        ReactionEvent.from_payload(event), runtime.slack, runtime
    )
    runtime.slack.send_channel_message.assert_not_called()


@pytest.mark.parametrize(
    ("event_type", "function", "event"),
    [
        (
            "app_mention",
            "mention_response",
            create_sample_app_mention_event("<@UANNA> help"),
        ),
        ("reaction_added", "join_bigchat", create_sample_reaction_added_event("gogo")),
        (
            "reaction_removed",
            "abandon_bigchat",
            {**create_sample_reaction_added_event("gogo"), "type": "reaction_removed"},
        ),
    ],
)
def test_handler_failures_are_reported_to_the_admin_channel_from_settings(
    monkeypatch, event_type, function, event
):
    runtime = fake_runtime(ADMIN_CHANNEL="C_ADMIN_FROM_RUNTIME")
    bolt_app = FakeBoltApp()
    app.create_app(runtime, bolt_app=bolt_app)
    module = ENTRYPOINT_MODULES[event_type]
    failure = RuntimeError("handler failed")
    monkeypatch.setattr(module, function, MagicMock(side_effect=failure))
    report = MagicMock()
    monkeypatch.setattr(module, "report_failure", report)

    ack = MagicMock()
    bolt_app.handlers["event", event_type](ack=ack, event=event, client=MagicMock())

    ack.assert_called_once_with()
    report.assert_called_once_with(
        runtime.slack, "C_ADMIN_FROM_RUNTIME", event, failure
    )


def test_mention_handler_hands_bolt_client_to_runtime(monkeypatch):
    runtime = fake_runtime()
    bolt_app = FakeBoltApp()
    app.create_app(runtime, bolt_app=bolt_app)
    dispatch = MagicMock()
    monkeypatch.setattr(app, "mention_response", dispatch)
    seen = []
    runtime.slack_client = lambda client: seen.append(client) or runtime.slack

    client = MagicMock(name="bolt-client")
    event = create_sample_app_mention_event("<@UANNA> help")
    bolt_app.handlers["event", "app_mention"](
        ack=MagicMock(), event=event, client=client
    )

    assert seen == [client]
    dispatch.assert_called_once()
    assert dispatch.call_args.args[0].text == event["text"]
    assert dispatch.call_args.args[1] is runtime.slack
    assert dispatch.call_args.args[2] is runtime


@pytest.mark.parametrize("bigchat_enabled", [False, True])
@pytest.mark.parametrize("digest_enabled", [False, True])
def test_schedulers_start_only_when_explicitly_requested(
    monkeypatch, bigchat_enabled, digest_enabled
):
    runtime = fake_runtime(
        BIGCHAT_REMINDER_ENABLED=bigchat_enabled,
        DAILY_DIGEST_ENABLED=digest_enabled,
    )
    reminders, digests = MagicMock(), MagicMock()
    monkeypatch.setattr(bigchat_jobs, "DailyScheduler", reminders)
    monkeypatch.setattr(community_jobs, "DailyScheduler", digests)
    app.create_app(runtime, bolt_app=FakeBoltApp())
    reminders.assert_not_called()
    digests.assert_not_called()

    app.start_schedulers(runtime)
    for enabled, factory, hour, name, job in (
        (
            bigchat_enabled,
            reminders,
            18,
            "bigchat-reminder",
            bigchat_jobs.remind_bigchat,
        ),
        (digest_enabled, digests, 10, "daily-digest", community_jobs.post_daily_digest),
    ):
        assert factory.call_count == int(enabled)
        if enabled:
            assert factory.call_args.kwargs["hour"] == hour
            assert factory.call_args.kwargs["minute"] == 0
            assert factory.call_args.kwargs["tz"] is KST
            assert factory.call_args.kwargs["name"] == name
            assert factory.call_args.kwargs["job"].func is job
            assert factory.call_args.kwargs["job"].args == (runtime,)
            factory.return_value.start.assert_called_once_with()
    assert untouched(runtime)


@pytest.mark.parametrize("module_name", ["anna_boot_test", "__main__"])
def test_gunicorn_and_local_entrypoints_initialize_the_app(monkeypatch, module_name):
    runtime = fake_runtime(LOGLEVEL="WARNING")
    flask_app = MagicMock()
    bolt_app = flask_app.extensions["slack_app"]
    factory = MagicMock(return_value=flask_app)
    schedulers = MagicMock()
    init_logger = MagicMock()
    monkeypatch.setattr("bootstrap.create_runtime", MagicMock(return_value=runtime))
    monkeypatch.setattr(app, "create_app", factory)
    monkeypatch.setattr(app, "start_schedulers", schedulers)
    monkeypatch.setattr("config.log_config.init_logger", init_logger)

    namespace = runpy.run_module("anna", run_name=module_name)
    assert namespace["runtime"] is runtime
    assert namespace["flask_app"] is flask_app
    assert namespace["app"] is bolt_app
    init_logger.assert_called_once_with("WARNING")
    factory.assert_called_once_with(runtime)
    schedulers.assert_called_once_with(runtime)
    if module_name == "__main__":
        flask_app.run.assert_called_once_with(host="0.0.0.0", port=8080)
    else:
        flask_app.run.assert_not_called()
