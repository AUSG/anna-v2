"""ACK, 명령 선택과 이벤트별 handler factory 연결을 검증한다."""

import json
from unittest.mock import MagicMock, create_autospec

import pytest

import anna
import slack_events
from features.bigchat.handlers.create_bigchat_modal import (
    CREATE_BIGCHAT_SHORTCUT_ID,
    CREATE_BIGCHAT_VIEW_ID,
)
from test.fixtures.anna import load_anna
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_message_shortcut_body,
    create_sample_reaction_added_event,
    create_sample_view_submission_body,
)

EXTERNAL_FACTORIES = ("sheets", "members", "github", "qa")
HANDLERS = (
    "HelpResponse",
    "ShuffleResponse",
    "QuestionResponse",
    "CreateIssue",
    "CreateBigchatSheet",
    "RemindBigchatCommand",
    "SimpleResponse",
)


@pytest.fixture
def runtime(monkeypatch):
    return load_anna(monkeypatch)


@pytest.fixture
def slack_client(monkeypatch):
    factory = create_autospec(slack_events.SlackClient, spec_set=True)
    factory.return_value.get_replies.return_value = []
    monkeypatch.setattr(slack_events, "SlackClient", factory)
    return factory.return_value


@pytest.fixture
def external_factories(monkeypatch, runtime):
    app, _, _ = runtime
    factories = {}
    for name in EXTERNAL_FACTORIES:
        factory = create_autospec(
            getattr(app.services, name),
            spec_set=True,
            side_effect=AssertionError(f"Unexpected dependency: {name}"),
        )
        monkeypatch.setattr(app.services, name, factory)
        factories[name] = factory
    return factories


def run_mention(runtime, text):
    _, bolt, _ = runtime
    event = create_sample_app_mention_event(text)
    say, web_client = MagicMock(), MagicMock()
    bolt.handlers["event", "app_mention"](
        ack=MagicMock(), event=event, say=say, client=web_client
    )
    return event, say, web_client


def test_help_executes_without_external_dependencies(
    runtime, slack_client, external_factories
):
    event, say, web_client = run_mention(runtime, "<@U01BN035Y6L> help")
    slack_events.SlackClient.assert_called_once_with(say, web_client)
    slack_client.send_message.assert_called_once()
    assert (
        "사용할 수 있는 명령어야" in slack_client.send_message.call_args.kwargs["msg"]
    )
    for factory in external_factories.values():
        factory.assert_not_called()
    slack_client.add_emoji.assert_called_once_with(
        event["channel"], event["ts"], "loading"
    )
    slack_client.remove_emoji.assert_called_once_with(
        event["channel"], event["ts"], "loading"
    )
    say.assert_not_called()


def test_explicit_question_with_command_keywords_reaches_qa(
    runtime, slack_client, external_factories
):
    question = "help 도움말 기능은 어떻게 구현돼있어?"
    qa_factory = external_factories["qa"]
    qa_factory.side_effect = None
    qa = qa_factory.return_value
    qa.chat.return_value = "질문에 대한 답변이야!"
    event, say, _ = run_mention(runtime, f"<@U01BN035Y6L> q) {question}")
    qa_factory.assert_called_once_with()
    qa.chat.assert_called_once()
    assert qa.chat.call_args.kwargs["question"] == question
    slack_client.send_answer.assert_called_once_with(
        answer="질문에 대한 답변이야!", sources=[], ts=event["ts"]
    )
    slack_client.send_message.assert_not_called()
    for name in ("sheets", "members", "github"):
        external_factories[name].assert_not_called()
    say.assert_not_called()


@pytest.mark.parametrize(
    "text,selected,dependencies,require_prefix",
    [
        ("help", "HelpResponse", (), None),
        ("shuffle", "ShuffleResponse", (), None),
        ("q) help", "QuestionResponse", ("qa",), True),
        ("다음 빅챗 언제야?", "QuestionResponse", ("qa",), False),
        ("새로운 이슈 버그", "CreateIssue", ("github",), None),
        (
            "새로운 빅챗 AI 밋업 26-08-20 19:00~21:00",
            "CreateBigchatSheet",
            ("sheets", "members"),
            None,
        ),
        (
            "빅챗 리마인더 테스트 <@UOTHER>",
            "RemindBigchatCommand",
            ("sheets", "members"),
            None,
        ),
        ("", "SimpleResponse", (), None),
    ],
)
def test_constructs_only_selected_handler_and_dependencies(
    text,
    selected,
    dependencies,
    require_prefix,
    monkeypatch,
    runtime,
    slack_client,
    external_factories,
):
    app, _, _ = runtime
    monkeypatch.setattr(app.settings, "ANNA_ID", "UANNA")
    monkeypatch.setattr(app.settings, "JOIN_BIGCHAT_EMOJI", "gogo")
    handlers = {}
    for name in HANDLERS:
        handlers[name] = create_autospec(getattr(anna, name), spec_set=True)
        monkeypatch.setattr(anna, name, handlers[name])
    for name in dependencies:
        external_factories[name].side_effect = None

    event, say, _ = run_mention(runtime, f"<@U01BN035Y6L> {text}")
    expected_args = (
        event,
        slack_client,
        *(external_factories[name].return_value for name in dependencies),
    )
    if selected == "CreateBigchatSheet":
        expected_args += ("gogo",)
    elif selected == "RemindBigchatCommand":
        expected_args += ("UANNA",)
    expected_kwargs = (
        {"require_prefix": require_prefix, "assistant_id": "UANNA"}
        if require_prefix is not None
        else {}
    )
    for name, factory in external_factories.items():
        if name in dependencies:
            factory.assert_called_once_with()
        else:
            factory.assert_not_called()
    for name, handler in handlers.items():
        if name == selected:
            handler.assert_called_once_with(*expected_args, **expected_kwargs)
            handler.return_value.handle_mention.assert_called_once_with()
        else:
            handler.assert_not_called()
    say.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_does_not_fall_through_when_selected_handler_returns_false_or_raises(
    fails,
    monkeypatch,
    runtime,
    slack_client,
    external_factories,
):
    help_factory = create_autospec(anna.HelpResponse, spec_set=True)
    help_factory.return_value.handle_mention.return_value = False
    if fails:
        help_factory.return_value.handle_mention.side_effect = RuntimeError(
            "handler failed"
        )
    fallback = create_autospec(anna.SimpleResponse, spec_set=True)
    monkeypatch.setattr(anna, "HelpResponse", help_factory)
    monkeypatch.setattr(anna, "SimpleResponse", fallback)
    _, say, _ = run_mention(runtime, "<@U01BN035Y6L> help")
    help_factory.assert_called_once()
    help_factory.return_value.handle_mention.assert_called_once_with()
    fallback.assert_not_called()
    for factory in external_factories.values():
        factory.assert_not_called()
    slack_client.add_emoji.assert_called_once()
    slack_client.remove_emoji.assert_called_once()
    assert say.call_count == (2 if fails else 0)


@pytest.mark.parametrize("event_type", ["app_mention", "message"])
@pytest.mark.parametrize(
    "edited", [{"edited": {"ts": "2"}}, {"subtype": "message_changed"}]
)
def test_edited_events_are_acked_without_constructing_handlers(
    monkeypatch,
    runtime,
    event_type,
    edited,
):
    _, bolt, _ = runtime
    factory = MagicMock(side_effect=AssertionError("edited event must be ignored"))
    monkeypatch.setattr(slack_events, "SlackClient", factory)
    ack = MagicMock()
    bolt.handlers["event", event_type](
        ack=ack, event={"ts": "1", **edited}, say=MagicMock(), client=MagicMock()
    )
    ack.assert_called_once_with()
    factory.assert_not_called()


@pytest.mark.parametrize(
    "event_type,handler_name",
    [
        ("reaction_added", "JoinBigchat"),
        ("reaction_removed", "AbandonBigchat"),
        ("app_mention", "HelpResponse"),
        ("channel_created", "AnnounceNewChannelCreated"),
        ("message", "SubinLikeResponse"),
    ],
)
def test_events_ack_before_constructing_handler(
    monkeypatch,
    runtime,
    event_type,
    handler_name,
    external_factories,
):
    _, bolt, _ = runtime
    trace = MagicMock()
    monkeypatch.setattr(anna, handler_name, trace.handler)
    for factory in external_factories.values():
        factory.side_effect = None
    event = create_sample_reaction_added_event("gogo")
    if event_type == "app_mention":
        event = create_sample_app_mention_event("<@U01BN035Y6L> help")
    elif event_type == "channel_created":
        event = {"channel": {"id": "C_NEW"}}
    bolt.handlers["event", event_type](
        ack=trace.ack, event=event, say=MagicMock(), client=MagicMock()
    )
    assert [call[0] for call in trace.mock_calls][:2] == ["ack", "handler"]
    assert trace.handler.call_args.args[0] is event
    method = "handle_mention" if event_type == "app_mention" else "run"
    getattr(trace.handler.return_value, method).assert_called_once_with()


@pytest.mark.parametrize("thread_ts", [None, "1688800000.000001"])
def test_shortcut_acks_before_opening_modal_and_anchors_to_root(
    monkeypatch, runtime, thread_ts
):
    _, bolt, _ = runtime
    trace = MagicMock()
    monkeypatch.setattr(anna, "OpenCreateBigchatModal", trace.handler)
    body = create_sample_message_shortcut_body(thread_ts=thread_ts)
    client = MagicMock()
    bolt.handlers["shortcut", CREATE_BIGCHAT_SHORTCUT_ID](
        ack=trace.ack, body=body, say=MagicMock(), client=client
    )
    event, web = trace.handler.call_args.args
    assert [call[0] for call in trace.mock_calls][:2] == ["ack", "handler"]
    assert event["channel"] == body["channel"]["id"]
    assert event["ts"] == (thread_ts or body["message"]["ts"])
    assert event["user"] == body["user"]["id"]
    assert web is client


def test_modal_submission_leaves_ack_to_feature_handler(
    monkeypatch, runtime, external_factories
):
    _, bolt, _ = runtime
    for factory in external_factories.values():
        factory.side_effect = None
    handler = MagicMock()
    monkeypatch.setattr(anna, "SubmitCreateBigchatModal", handler)
    ack = MagicMock()
    body = create_sample_view_submission_body("AI 밋업", "2026-08-20", "19:00", "21:00")
    bolt.handlers["view", CREATE_BIGCHAT_VIEW_ID](
        ack=ack, body=body, say=MagicMock(), client=MagicMock()
    )
    ack.assert_not_called()
    assert handler.call_args.args[1] is ack
    handler.return_value.run.assert_called_once_with()


@pytest.mark.parametrize("kind", ["modal", "shortcut"])
def test_interaction_failures_notify_admin_and_requester(
    monkeypatch, runtime, external_factories, kind
):
    _, bolt, _ = runtime
    for factory in external_factories.values():
        factory.side_effect = None
    handler = MagicMock()
    handler.return_value.run.side_effect = RuntimeError("처리 실패")
    if kind == "modal":
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )
        metadata = json.loads(body["view"]["private_metadata"])
        channel, ts = metadata["channel"], metadata["thread_ts"]
        monkeypatch.setattr(anna, "SubmitCreateBigchatModal", handler)
        callback = bolt.handlers["view", CREATE_BIGCHAT_VIEW_ID]
    else:
        body = create_sample_message_shortcut_body()
        channel, ts = body["channel"]["id"], body["message"]["ts"]
        monkeypatch.setattr(anna, "OpenCreateBigchatModal", handler)
        callback = bolt.handlers["shortcut", CREATE_BIGCHAT_SHORTCUT_ID]
    say = MagicMock()
    callback(ack=MagicMock(), body=body, say=say, client=MagicMock())
    assert say.call_count == 2
    assert say.call_args_list[0].kwargs["channel"] == "C_ADMIN"
    assert say.call_args.kwargs["channel"] == channel
    assert say.call_args.kwargs["thread_ts"] == ts
    assert "요청이 정상적으로 처리되지 않았어" in say.call_args.kwargs["text"]


def test_calendar_button_is_acked_without_other_actions(runtime):
    _, bolt, _ = runtime
    callback = next(
        handler for (kind, _), handler in bolt.handlers.items() if kind == "action"
    )
    ack = MagicMock()
    callback(ack=ack)
    ack.assert_called_once_with()
