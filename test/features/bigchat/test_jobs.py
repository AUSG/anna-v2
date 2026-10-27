from datetime import date
from unittest.mock import MagicMock

import pytest
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from features.bigchat import jobs
from features.bigchat.models import ReminderResult
from test.fixtures.runtime import fake_runtime


@pytest.fixture
def runtime():
    runtime = fake_runtime()
    # slack_client() 가 잡 전용 WebClient 를 받는지 보기 위해 호출을 기록한다
    runtime.slack_client = MagicMock(side_effect=runtime.slack_client)
    return runtime


@pytest.fixture
def reminder(monkeypatch):
    reminder = MagicMock()
    reminder.return_value.run.return_value = ReminderResult(
        date(2026, 8, 20), sent_cnt=2
    )
    monkeypatch.setattr(jobs, "RemindBigchat", reminder)
    return reminder


def test_scheduled_reminder_uses_service_and_rate_limit_retry(runtime, reminder):
    jobs.remind_bigchat(runtime)

    (web_client,) = runtime.web_clients
    runtime.slack_client.assert_called_once_with(web_client)
    # 여러 명에게 연속으로 DM 을 보내다 429 를 맞으면 Retry-After 만큼 기다렸다 재시도한다
    web_client.retry_handlers.append.assert_called_once()
    retry = web_client.retry_handlers.append.call_args.args[0]
    assert isinstance(retry, RateLimitErrorRetryHandler)
    assert retry.max_retry_count == 2
    reminder.assert_called_once_with(runtime.slack, runtime.sheets(), runtime.members())
    reminder.return_value.run.assert_called_once_with()
    runtime.slack.send_channel_message.assert_not_called()


def test_scheduled_reminder_reports_service_failure_to_admin(runtime, reminder):
    reminder.return_value.run.side_effect = RuntimeError("reminder failed")

    jobs.remind_bigchat(runtime)

    runtime.slack.send_channel_message.assert_called_once()
    channel, text = runtime.slack.send_channel_message.call_args.args
    assert channel == "C_ADMIN"
    assert "빅챗 리마인더 DM 발송" in text
    assert "RuntimeError: reminder failed" in text


def test_scheduled_reminder_does_not_raise_if_admin_notification_also_fails(
    runtime, reminder
):
    reminder.return_value.run.side_effect = RuntimeError("reminder failed")
    runtime.slack.send_channel_message.side_effect = RuntimeError("Slack failed")

    jobs.remind_bigchat(runtime)

    runtime.slack.send_channel_message.assert_called_once()
