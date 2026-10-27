"""앱 조립, 의존성 수명과 명시적인 worker 시작을 검증한다."""

import importlib
import importlib.util
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import anna
from config.env_config import Settings
from features.bigchat.calendar import KST
from slack_events import SlackContext
from test.fixtures.anna import FakeBoltApp, load_anna
from test.fixtures.slack_events import create_sample_app_mention_event


@pytest.mark.parametrize("reminders", [False, True])
@pytest.mark.parametrize("digest", [False, True])
def test_schedulers_start_only_explicitly_and_once(monkeypatch, reminders, digest):
    runtime, _, scheduler = load_anna(monkeypatch, reminders=reminders, digest=digest)
    scheduler.assert_not_called()
    expected = [
        (name, hour)
        for enabled, name, hour in (
            (reminders, "bigchat-reminder", 18),
            (digest, "daily-digest", 10),
        )
        if enabled
    ]
    jobs = runtime.flask_app.extensions["anna_jobs"]
    assert [(job.name, job.hour) for job in jobs] == expected
    anna.start_jobs(runtime.flask_app)
    anna.start_jobs(runtime.flask_app)
    assert scheduler.call_count == len(expected)
    assert scheduler.return_value.start.call_count == len(expected)
    for call, job in zip(scheduler.call_args_list, jobs):
        assert call.kwargs == dict(
            job=job.callback, hour=job.hour, minute=0, tz=KST, name=job.name
        )


def test_scheduler_start_retry_does_not_restart_successful_jobs(monkeypatch):
    runtime, _, _ = load_anna(monkeypatch, reminders=True, digest=True)
    reminder, failed_digest, digest = MagicMock(), MagicMock(), MagicMock()
    failed_digest.start.side_effect = RuntimeError("thread start failed")
    scheduler = MagicMock(side_effect=[reminder, failed_digest, digest])
    monkeypatch.setattr(anna, "DailyScheduler", scheduler)
    with pytest.raises(RuntimeError, match="thread start failed"):
        anna.start_jobs(runtime.flask_app)
    anna.start_jobs(runtime.flask_app)
    reminder.start.assert_called_once_with()
    digest.start.assert_called_once_with()
    assert [call.kwargs["name"] for call in scheduler.call_args_list] == [
        "bigchat-reminder",
        "daily-digest",
        "daily-digest",
    ]


def test_factory_passes_settings_to_bolt_and_logger(monkeypatch):
    settings = Settings(
        _env_file=None,
        SLACK_BOT_TOKEN="xoxb-configured",
        SLACK_SIGNING_SECRET="configured-secret",
        LOGLEVEL="INFO",
    )
    bolt = MagicMock(return_value=FakeBoltApp())
    logger = MagicMock()
    monkeypatch.setattr(anna, "App", bolt)
    monkeypatch.setattr(anna, "init_logger", logger)
    app = anna.create_app(settings)
    bolt.assert_called_once_with(
        token="xoxb-configured", signing_secret="configured-secret"
    )
    logger.assert_called_once_with("INFO")
    assert app.extensions["anna_services"].settings is settings


def test_create_app_does_not_construct_external_clients(monkeypatch):
    for name in (
        "GoogleSpreadsheetClient",
        "MemberManager",
        "QAClient",
        "GithubClient",
        "WebClient",
    ):
        monkeypatch.setattr(
            anna, name, MagicMock(side_effect=AssertionError(f"eager {name}"))
        )
    runtime, bolt, scheduler = load_anna(monkeypatch, reminders=True, digest=True)
    assert runtime.flask_app.test_client().get("/health").json == {"status": "ok"}
    assert {selector for kind, selector in bolt.handlers if kind == "event"} == {
        "reaction_added",
        "reaction_removed",
        "app_mention",
        "channel_created",
        "message",
    }
    scheduler.assert_not_called()
    for name in (
        "GoogleSpreadsheetClient",
        "MemberManager",
        "QAClient",
        "GithubClient",
        "WebClient",
    ):
        getattr(anna, name).assert_not_called()


def test_services_are_lazy_shared_per_app_and_initialize_once_across_threads(
    monkeypatch,
):
    settings = Settings(_env_file=None, MEMBERS_INFO_WORKSHEET_ID=123)
    sheets, members, qa = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(anna, "GoogleSpreadsheetClient", sheets)
    monkeypatch.setattr(anna, "MemberManager", members)
    monkeypatch.setattr(anna, "QAClient", qa)
    members.side_effect = [MagicMock(), MagicMock()]
    qa.side_effect = [MagicMock(), MagicMock()]
    first, second = anna.Services(settings), anna.Services(settings)
    sheets.assert_not_called()
    members.assert_not_called()
    qa.assert_not_called()
    with ThreadPoolExecutor(max_workers=4) as executor:
        member_results = list(executor.map(lambda _: first.members(), range(8)))
        qa_results = list(executor.map(lambda _: first.qa(), range(8)))
    assert all(result is member_results[0] for result in member_results)
    assert all(result is qa_results[0] for result in qa_results)
    members.assert_called_once_with(sheets.return_value, worksheet_id=123)
    qa.assert_called_once_with(
        qa_server_base_url=settings.QA_SERVER_BASE_URL, api_key=settings.QA_API_KEY
    )
    assert second.members() is not member_results[0]
    assert second.qa() is not qa_results[0]
    assert members.call_count == qa.call_count == 2
    first.sheets()
    first.sheets()
    assert sheets.call_count == 4  # 앱별 회원 클라이언트 둘 + 직접 조회 둘
    for call in sheets.call_args_list:
        assert call.kwargs == {"settings": settings}


def test_handlers_and_slack_context_are_event_scoped():
    settings = Settings(_env_file=None)
    handlers = anna.build_slack_handlers(anna.Services(settings))
    event1 = create_sample_app_mention_event("help")
    event2 = {**event1, "text": "도움", "ts": "different"}
    context1 = SlackContext(event1, MagicMock(), MagicMock(), MagicMock())
    context2 = SlackContext(event2, MagicMock(), MagicMock(), MagicMock())
    first = handlers.mentions["help"](context1)
    second = handlers.mentions["help"](context2)
    assert first is not second
    assert first.ts == event1["ts"] and second.ts == "different"
    assert first.slack_client is context1.slack_client
    assert second.slack_client is context2.slack_client


def test_separate_apps_have_separate_services_and_schedulers(monkeypatch):
    monkeypatch.setattr(anna, "init_logger", MagicMock())
    settings = Settings(
        _env_file=None, BIGCHAT_REMINDER_ENABLED=False, DAILY_DIGEST_ENABLED=False
    )
    first = anna.create_app(settings, bolt_app=FakeBoltApp())
    second = anna.create_app(settings, bolt_app=FakeBoltApp())
    assert first.extensions["anna_services"] is not second.extensions["anna_services"]
    assert (
        first.extensions["anna_schedulers"] is not second.extensions["anna_schedulers"]
    )


def test_concurrent_start_calls_do_not_duplicate_schedulers(monkeypatch):
    runtime, _, scheduler = load_anna(monkeypatch, reminders=True, digest=True)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: anna.start_jobs(runtime.flask_app), range(8)))
    assert scheduler.call_count == 2
    assert scheduler.return_value.start.call_count == 2


def test_gunicorn_worker_hook_starts_jobs_only_after_app_is_loaded(monkeypatch):
    start = MagicMock()
    monkeypatch.setattr(anna, "start_jobs", start)
    config = importlib.import_module("gunicorn_config")
    importlib.reload(config)
    start.assert_not_called()
    worker = MagicMock()
    config.post_worker_init(worker)
    start.assert_called_once_with(worker.wsgi)


def test_import_does_not_initialize_bolt_clients_or_scheduler(monkeypatch):
    bolt, web_client, start_thread = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr("slack_bolt.App", bolt)
    monkeypatch.setattr("slack_sdk.WebClient", web_client)
    monkeypatch.setattr("threading.Thread.start", start_thread)
    spec = importlib.util.spec_from_file_location("anna_import_check", anna.__file__)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)

    spec.loader.exec_module(module)

    bolt.assert_not_called()
    web_client.assert_not_called()
    start_thread.assert_not_called()
    assert not hasattr(module, "flask_app")


def test_gunicorn_loads_factory_and_starts_jobs_only_in_worker_hook(monkeypatch):
    from gunicorn.app.wsgiapp import WSGIApplication

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "gunicorn",
            "--config",
            "src/gunicorn_config.py",
            "--chdir",
            "src",
            "anna:create_app()",
        ],
    )
    monkeypatch.delenv("GUNICORN_CMD_ARGS", raising=False)
    monkeypatch.setattr(anna.envs, "BIGCHAT_REMINDER_ENABLED", True)
    monkeypatch.setattr(anna.envs, "DAILY_DIGEST_ENABLED", True)
    monkeypatch.setattr(anna, "App", MagicMock(return_value=FakeBoltApp()))
    monkeypatch.setattr(anna, "init_logger", MagicMock())
    scheduler = MagicMock()
    monkeypatch.setattr(anna, "DailyScheduler", scheduler)

    application = WSGIApplication()
    app = application.wsgi()

    assert app.test_client().get("/health").json == {"status": "ok"}
    scheduler.assert_not_called()
    worker = MagicMock(wsgi=app)
    application.cfg.post_worker_init(worker)
    assert scheduler.call_count == 2
    assert scheduler.return_value.start.call_count == 2
