"""선택된 핸들러의 실행과 의존성 생성·오류 처리 경계를 검증한다."""

from unittest.mock import MagicMock, create_autospec

import pytest
from slack_sdk import WebClient

import app
import bootstrap
from config.env_config import Settings
from features.bigchat.services.commands import CreateBigchat, Reminder
from features.bot_commands.models import Shuffle
from features.bot_commands.presentation.messages import HELP_MESSAGE
from features.issues.models import CreateIssue
from features.members.services.directory import MemberManager
from features.questions.models import ChatResult, Question
from integrations.slack import SlackClient
from shared.loading_emoji import EMOJI_NAME
from shared.slack_events import MentionEvent
from test.fixtures.runtime import fake_runtime, fake_settings
from test.fixtures.slack_events import create_sample_app_mention_event

COLLABORATORS = ("sheets", "members", "qa", "github")
# (핸들러를 가진 모듈, 함수 이름). app 이 import 한 모듈 객체에 patch 한다.
HANDLERS = {
    "show_help": (app.bot_commands, "show_help"),
    "shuffle_users": (app.bot_commands, "shuffle_users"),
    "unknown_command": (app.bot_commands, "unknown_command"),
    "answer_question": (app.questions, "answer_question"),
    "create_issue": (app.issues, "create_issue"),
    "create_from_mention": (app.bigchat, "create_from_mention"),
    "remind_now": (app.bigchat, "remind_now"),
}


@pytest.fixture
def runtime():
    """collaborator 접근자를 감싸 어떤 의존성이 실제로 요청됐는지 기록한다."""
    runtime = fake_runtime()
    runtime.touched = []
    for name in COLLABORATORS:
        original = getattr(runtime, name)

        def accessor(name=name, original=original):
            runtime.touched.append(name)
            return original()

        setattr(runtime, name, accessor)
    return runtime


@pytest.fixture
def handlers(monkeypatch):
    patched = {}
    for name, (module, attribute) in HANDLERS.items():
        patched[name] = create_autospec(getattr(module, attribute), spec_set=True)
        monkeypatch.setattr(module, attribute, patched[name])
    return patched


def run_mention(runtime, text):
    event = MentionEvent.from_payload(create_sample_app_mention_event(text))
    result = app.mention_response(event, runtime.slack, runtime)
    return event, result


def test_help_executes_without_external_dependencies(runtime):
    # 실제 핸들러와의 연결은 대표 명령 하나로, 명령별 생성 여부는 아래 행렬로 검증한다.
    event, result = run_mention(runtime, "<@UANNA> help")

    assert result is True
    runtime.slack.send_thread_message.assert_called_once_with(
        event.channel, event.ts, HELP_MESSAGE
    )
    assert "사용할 수 있는 명령어야" in HELP_MESSAGE
    assert runtime.touched == []
    runtime.slack.add_reaction.assert_called_once_with(
        event.channel, event.ts, EMOJI_NAME
    )
    runtime.slack.remove_reaction.assert_called_once_with(
        event.channel, event.ts, EMOJI_NAME
    )
    runtime.slack.send_channel_message.assert_not_called()  # 관리자 오류 보고가 없어야 한다


def test_loading_emoji_wraps_the_dispatch(runtime):
    event, _ = run_mention(runtime, "<@UANNA> help")
    names = [name for name, _, _ in runtime.slack.mock_calls]
    assert names == ["add_reaction", "send_thread_message", "remove_reaction"]


def test_explicit_question_with_command_keywords_reaches_qa(runtime):
    # 분류뿐 아니라 실제 answer_question 이 명령 키워드를 포함한 질문도 수락해야 한다.
    question = "help 도움말 기능은 어떻게 구현돼있어?"
    qa = runtime.qa()
    runtime.touched.clear()
    qa.chat.return_value = ChatResult(answer="질문에 대한 답변이야!")

    event, result = run_mention(runtime, f"<@UANNA> q) {question}")

    assert result is True
    assert runtime.touched == ["qa"]
    qa.chat.assert_called_once()
    assert qa.chat.call_args.kwargs["question"] == question
    runtime.slack.send_answer.assert_called_once_with(
        event.channel, event.ts, "질문에 대한 답변이야!", []
    )
    runtime.slack.send_thread_message.assert_not_called()


@pytest.mark.parametrize(
    ("text", "selected", "touched", "command"),
    [
        ("help", "show_help", (), None),
        ("shuffle <@UOTHER>", "shuffle_users", (), Shuffle(("UOTHER",))),
        ("q) help", "answer_question", ("qa",), Question("help", explicit=True)),
        (
            "다음 빅챗 언제야?",
            "answer_question",
            ("qa",),
            Question("다음 빅챗 언제야?", explicit=False),
        ),
        ("새로운 이슈 버그", "create_issue", ("github",), CreateIssue("버그")),
        (
            "새로운 빅챗 AI 밋업 26-08-20 19:00~21:00",
            "create_from_mention",
            (),
            CreateBigchat("AI 밋업 26-08-20 19:00~21:00"),
        ),
        ("빅챗 리마인더 테스트 <@UOTHER>", "remind_now", (), Reminder("test", ("UOTHER",))),
        ("", "unknown_command", (), None),
    ],
)
def test_calls_only_the_selected_handler_with_its_dependencies(
    runtime, handlers, text, selected, touched, command
):
    handlers[selected].return_value = True

    event, result = run_mention(runtime, f"<@UANNA> {text}")

    assert result is True
    assert runtime.touched == list(touched)
    slack = runtime.slack
    expected = {
        "show_help": ((event, slack), {}),
        "unknown_command": ((event, slack), {}),
        "shuffle_users": ((command, event, slack), {}),
        "answer_question": (
            (command, event, slack, runtime.qa()),
            {"assistant_id": runtime.settings.ANNA_ID},
        ),
        "create_issue": ((command, event, slack, runtime.github()), {}),
        "create_from_mention": ((command, event, slack, runtime), {}),
        "remind_now": ((command, event, slack, runtime), {}),
    }[selected]
    for name, handler in handlers.items():
        if name == selected:
            handler.assert_called_once_with(*expected[0], **expected[1])
        else:
            handler.assert_not_called()
    slack.add_reaction.assert_called_once_with(event.channel, event.ts, EMOJI_NAME)
    slack.remove_reaction.assert_called_once_with(event.channel, event.ts, EMOJI_NAME)


@pytest.mark.parametrize("fails", [False, True])
def test_does_not_fall_through_when_selected_handler_returns_false_or_raises(
    runtime, handlers, fails
):
    handlers["show_help"].return_value = False
    if fails:
        handlers["show_help"].side_effect = RuntimeError("handler failed")

    if fails:
        with pytest.raises(RuntimeError, match="handler failed"):
            run_mention(runtime, "<@UANNA> help")
    else:
        _, result = run_mention(runtime, "<@UANNA> help")
        assert result is False

    handlers["show_help"].assert_called_once()
    for name, handler in handlers.items():
        if name != "show_help":
            handler.assert_not_called()
    assert runtime.touched == []
    runtime.slack.add_reaction.assert_called_once()
    runtime.slack.remove_reaction.assert_called_once()


def test_unknown_command_type_is_rejected(runtime, handlers):
    event = MentionEvent.from_payload(create_sample_app_mention_event("<@UANNA> help"))
    with pytest.raises(ValueError, match="Unknown mention command"):
        app.dispatch_mention(object(), event, runtime.slack, runtime)
    for handler in handlers.values():
        handler.assert_not_called()


# --- create_runtime ---------------------------------------------------------------


@pytest.fixture
def integrations(monkeypatch):
    patched = {}
    for name in ("GoogleSpreadsheetClient", "QAClient", "GithubClient"):
        patched[name] = create_autospec(getattr(bootstrap, name), spec_set=True)
        monkeypatch.setattr(bootstrap, name, patched[name])
    return patched


def production_settings():
    values = vars(fake_settings())
    return Settings(_env_file=None, **values)


def test_create_runtime_shares_clients_and_builds_github_from_settings(integrations):
    settings = production_settings()
    runtime = bootstrap.create_runtime(settings)

    assert isinstance(runtime, bootstrap.ProductionRuntime)
    assert runtime.settings is settings
    for factory in integrations.values():
        factory.assert_not_called()  # 외부 클라이언트는 처음 쓰일 때 만든다

    assert runtime.sheets() is runtime.sheets()
    integrations["GoogleSpreadsheetClient"].assert_called_once_with(settings)
    assert runtime.sheets() is integrations["GoogleSpreadsheetClient"].return_value

    members = runtime.members()
    assert members is runtime.members()
    assert isinstance(members, MemberManager)
    assert members.sheets is runtime.sheets()
    assert members.members_worksheet_id == settings.MEMBERS_INFO_WORKSHEET_ID
    assert integrations["GoogleSpreadsheetClient"].call_count == 1

    assert runtime.qa() is runtime.qa()
    integrations["QAClient"].assert_called_once_with(
        qa_server_base_url=settings.QA_SERVER_BASE_URL, api_key=settings.QA_API_KEY
    )

    github = runtime.github()
    assert github is integrations["GithubClient"].return_value
    integrations["GithubClient"].assert_called_once_with(
        settings.GITHUB_TOKEN, settings.GITHUB_REPO
    )


def test_create_runtime_wraps_slack_clients_without_network(integrations):
    runtime = bootstrap.create_runtime(production_settings())
    web_client = runtime.web_client()
    assert isinstance(web_client, WebClient)
    assert web_client.token == runtime.settings.SLACK_BOT_TOKEN

    bolt_client = MagicMock(spec=WebClient)
    slack = runtime.slack_client(bolt_client)
    assert isinstance(slack, SlackClient)
    assert slack.web_client is bolt_client
    for factory in integrations.values():
        factory.assert_not_called()


def test_create_runtime_reads_settings_once_when_none_given(monkeypatch, integrations):
    settings = production_settings()
    factory = MagicMock(return_value=settings)
    monkeypatch.setattr(bootstrap, "Settings", factory)
    runtime = bootstrap.create_runtime()
    factory.assert_called_once_with()
    assert runtime.settings is settings
