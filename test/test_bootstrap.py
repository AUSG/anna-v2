"""선택된 핸들러의 실행과 의존성 생성·오류 처리 경계를 검증한다."""

from unittest.mock import MagicMock, create_autospec

import pytest

import app
import bootstrap as controller
from test.fixtures.slack_events import create_sample_app_mention_event

EXTERNAL_FACTORIES = (
    "GoogleSpreadsheetClient",
    "_get_member_manager",
    "GithubClient",
    "_get_qa_client",
)
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
def slack_client(monkeypatch):
    factory = create_autospec(controller.SlackClient, spec_set=True)
    factory.return_value.get_replies.return_value = []
    monkeypatch.setattr(controller, "SlackClient", factory)
    return factory.return_value


@pytest.fixture
def external_factories(monkeypatch):
    factories = {}
    for name in EXTERNAL_FACTORIES:
        factory = create_autospec(
            getattr(controller, name),
            spec_set=True,
            side_effect=AssertionError(f"Unexpected dependency: {name}"),
        )
        monkeypatch.setattr(controller, name, factory)
        factories[name] = factory
    return factories


def run_mention(text):
    event = create_sample_app_mention_event(text)
    say, web_client = MagicMock(), MagicMock()
    app.mention_response(
        event=event, say=say, client=web_client, dependencies=controller
    )
    return event, say, web_client


def test_help_executes_without_external_dependencies(slack_client, external_factories):
    # 실제 핸들러와의 연결은 대표 명령 하나로, 명령별 생성 여부는 아래 행렬로 검증한다.
    event, say, web_client = run_mention("<@U01BN035Y6L> help")

    controller.SlackClient.assert_called_once_with(say, web_client)
    slack_client.send_message.assert_called_once()
    assert "사용할 수 있는 명령어야" in slack_client.send_message.call_args.kwargs["msg"]
    for factory in external_factories.values():
        factory.assert_not_called()
    slack_client.add_emoji.assert_called_once_with(
        event["channel"], event["ts"], "loading"
    )
    slack_client.remove_emoji.assert_called_once_with(
        event["channel"], event["ts"], "loading"
    )
    say.assert_not_called()  # 전역 오류 안내가 발생하지 않아야 한다


def test_explicit_question_with_command_keywords_reaches_qa(
    slack_client, external_factories
):
    # 분류뿐 아니라 실제 QuestionResponse가 명령 키워드를 포함한 질문도 수락해야 한다.
    question = "help 도움말 기능은 어떻게 구현돼있어?"
    qa_factory = external_factories["_get_qa_client"]
    qa_factory.side_effect = None
    qa = qa_factory.return_value
    qa.chat.return_value = "질문에 대한 답변이야!"

    event, say, _ = run_mention(f"<@U01BN035Y6L> q) {question}")

    qa_factory.assert_called_once_with()
    qa.chat.assert_called_once()
    assert qa.chat.call_args.kwargs["question"] == question
    slack_client.send_answer.assert_called_once_with(
        answer="질문에 대한 답변이야!", sources=[], ts=event["ts"]
    )
    slack_client.send_message.assert_not_called()
    for name in ("GoogleSpreadsheetClient", "_get_member_manager", "GithubClient"):
        external_factories[name].assert_not_called()
    say.assert_not_called()


@pytest.mark.parametrize(
    ("text", "selected", "dependencies", "require_prefix"),
    [
        ("help", "HelpResponse", (), None),
        ("shuffle", "ShuffleResponse", (), None),
        ("q) help", "QuestionResponse", ("_get_qa_client",), True),
        ("다음 빅챗 언제야?", "QuestionResponse", ("_get_qa_client",), False),
        ("새로운 이슈 버그", "CreateIssue", ("GithubClient",), None),
        (
            "새로운 빅챗 AI 밋업 26-08-20 19:00~21:00",
            "CreateBigchatSheet",
            ("GoogleSpreadsheetClient", "_get_member_manager"),
            None,
        ),
        (
            "빅챗 리마인더 테스트 <@UOTHER>",
            "RemindBigchatCommand",
            ("GoogleSpreadsheetClient", "_get_member_manager"),
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
    slack_client,
    external_factories,
):
    # 서로 다른 값을 사용해야 봇 ID와 참여 이모지를 바꾸는 오류도 검출할 수 있다.
    monkeypatch.setattr(controller.envs, "ANNA_ID", "UANNA")
    monkeypatch.setattr(controller.envs, "JOIN_BIGCHAT_EMOJI", "gogo")
    handlers = {}
    for name in HANDLERS:
        handlers[name] = create_autospec(getattr(controller, name), spec_set=True)
        monkeypatch.setattr(controller, name, handlers[name])
    for name in dependencies:
        external_factories[name].side_effect = None

    event, say, _ = run_mention(f"<@U01BN035Y6L> {text}")
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
            if name == "GithubClient":
                factory.assert_called_once_with(
                    controller.envs.GITHUB_TOKEN, controller.envs.GITHUB_REPO
                )
            else:
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
    fails, monkeypatch, slack_client, external_factories
):
    help_factory = create_autospec(controller.HelpResponse, spec_set=True)
    help_handler = help_factory.return_value
    help_handler.handle_mention.return_value = False
    if fails:
        help_handler.handle_mention.side_effect = RuntimeError("handler failed")
    fallback = create_autospec(controller.SimpleResponse, spec_set=True)
    monkeypatch.setattr(controller, "HelpResponse", help_factory)
    monkeypatch.setattr(controller, "SimpleResponse", fallback)

    _, say, _ = run_mention("<@U01BN035Y6L> help")

    help_factory.assert_called_once()
    help_handler.handle_mention.assert_called_once_with()
    fallback.assert_not_called()
    for factory in external_factories.values():
        factory.assert_not_called()
    slack_client.add_emoji.assert_called_once()
    slack_client.remove_emoji.assert_called_once()
    assert say.call_count == (2 if fails else 0)
