"""예약 작업의 의존성 연결, 발송과 오류 알림을 검증한다."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

import anna
from config.env_config import Settings
from integrations.slack import NO_UNFURL
from jobs import post_daily_digest, remind_bigchat


@pytest.fixture
def web():
    client = MagicMock()
    client.retry_handlers = []
    return client


def test_reminder_uses_fresh_web_client_and_rate_limit_retry(web):
    factory = MagicMock(return_value=web)
    send = MagicMock(return_value=SimpleNamespace(sent_cnt=3))
    remind_bigchat(
        web_client_factory=factory, send_reminders=send, admin_channel="C_ADMIN"
    )
    factory.assert_called_once_with()
    send.assert_called_once()
    slack = send.call_args.args[0]
    assert slack.say is None and slack.web_client is web
    assert len(web.retry_handlers) == 1
    assert isinstance(web.retry_handlers[0], RateLimitErrorRetryHandler)
    assert web.retry_handlers[0].max_retry_count == 2
    web.chat_postMessage.assert_not_called()


@pytest.mark.parametrize("admin_fails", [False, True])
def test_reminder_failure_notifies_admin_and_does_not_escape(web, admin_fails):
    send = MagicMock(side_effect=RuntimeError("reminder failed"))
    if admin_fails:
        web.chat_postMessage.side_effect = RuntimeError("admin unavailable")
    remind_bigchat(
        web_client_factory=lambda: web, send_reminders=send, admin_channel="C_ADMIN"
    )
    web.chat_postMessage.assert_called_once()
    call = web.chat_postMessage.call_args.kwargs
    assert call["channel"] == "C_ADMIN"
    assert "reminder failed" in call["text"]
    assert "빅챗 리마인더 DM 발송 중 에러" in call["text"]
    assert call.items() >= NO_UNFURL.items()


def test_digest_posts_to_configured_channel(web):
    fetch = MagicMock(return_value="어제의 핫스레드")
    post_daily_digest(
        web_client_factory=lambda: web,
        fetch_digest=fetch,
        channel="C_DIGEST",
        admin_channel="C_ADMIN",
    )
    fetch.assert_called_once_with()
    web.chat_postMessage.assert_called_once()
    assert web.chat_postMessage.call_args.kwargs["channel"] == "C_DIGEST"
    assert web.chat_postMessage.call_args.kwargs["text"] == "어제의 핫스레드"


@pytest.mark.parametrize("text", ["", None])
def test_empty_digest_does_not_post(web, text):
    post_daily_digest(
        web_client_factory=lambda: web,
        fetch_digest=lambda: text,
        channel="C_DIGEST",
        admin_channel="C_ADMIN",
    )
    web.chat_postMessage.assert_not_called()


@pytest.mark.parametrize("failure", ["fetch", "post", "admin"])
def test_digest_failure_notifies_admin_and_does_not_escape(web, failure):
    fetch = MagicMock(return_value="핫스레드")
    if failure in ("fetch", "admin"):
        fetch.side_effect = RuntimeError("digest unavailable")
    if failure == "post":
        web.chat_postMessage.side_effect = [RuntimeError("Slack unavailable"), {}]
    elif failure == "admin":
        web.chat_postMessage.side_effect = RuntimeError("admin unavailable")
    post_daily_digest(
        web_client_factory=lambda: web,
        fetch_digest=fetch,
        channel="C_DIGEST",
        admin_channel="C_ADMIN",
    )
    assert web.chat_postMessage.call_args.kwargs["channel"] == "C_ADMIN"
    assert (
        "데일리 핫스레드 게시 중 에러" in web.chat_postMessage.call_args.kwargs["text"]
    )


def test_job_factories_remain_lazy_and_use_app_services(monkeypatch, web):
    settings = Settings(
        _env_file=None,
        ADMIN_CHANNEL="C_ADMIN",
        DAILY_DIGEST_CHANNEL_ID="C_DIGEST",
        BIGCHAT_REMINDER_ENABLED=True,
        DAILY_DIGEST_ENABLED=True,
    )
    services = MagicMock()
    services.settings = settings
    services.web_client.return_value = web
    services.qa.return_value.daily_digest.return_value = "핫스레드"
    reminder = MagicMock()
    reminder.return_value.run.return_value = SimpleNamespace(sent_cnt=1)
    monkeypatch.setattr(anna, "RemindBigchat", reminder)
    jobs = {job.name: job for job in anna.build_jobs(services)}
    for name in ("sheets", "members", "qa", "web_client"):
        getattr(services, name).assert_not_called()
    jobs["bigchat-reminder"].callback()
    reminder.assert_called_once()
    assert reminder.call_args.args[1:] == (
        services.sheets.return_value,
        services.members.return_value,
    )
    reminder.return_value.run.assert_called_once_with()
    jobs["daily-digest"].callback()
    services.qa.assert_called_once_with()
    services.qa.return_value.daily_digest.assert_called_once_with()
    assert services.web_client.call_count == 2
    assert web.chat_postMessage.call_args.kwargs["channel"] == "C_DIGEST"
