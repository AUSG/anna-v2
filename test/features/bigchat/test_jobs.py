from unittest.mock import MagicMock

from features.bigchat import jobs
from features.bigchat.models import ReminderResult
from datetime import date
from test.fixtures.runtime import fake_dependencies


def test_scheduled_reminder_uses_service_and_rate_limit_retry(monkeypatch):
    dependencies = fake_dependencies()
    reminder = MagicMock()
    reminder.return_value.run.return_value = ReminderResult(
        date(2026, 8, 20), sent_cnt=2
    )
    monkeypatch.setattr(jobs, "RemindBigchat", reminder)

    jobs.remind_bigchat(dependencies)

    web_client = dependencies.create_web_client.return_value
    dependencies.SlackClient.assert_called_once_with(None, web_client)
    reminder.assert_called_once_with(
        dependencies.SlackClient.return_value,
        dependencies.GoogleSpreadsheetClient.return_value,
        dependencies._get_member_manager.return_value,
    )
    retry = web_client.retry_handlers.append.call_args.args[0]
    assert retry.max_retry_count == 2
    reminder.return_value.run.assert_called_once_with()
    web_client.chat_postMessage.assert_not_called()


def test_scheduled_reminder_reports_service_failure_to_admin(monkeypatch):
    dependencies = fake_dependencies()
    reminder = MagicMock()
    reminder.return_value.run.side_effect = RuntimeError("reminder failed")
    monkeypatch.setattr(jobs, "RemindBigchat", reminder)

    jobs.remind_bigchat(dependencies)

    notification = (
        dependencies.create_web_client.return_value.chat_postMessage.call_args.kwargs
    )
    assert notification["channel"] == "C_ADMIN"
    assert "reminder failed" in notification["text"]
    assert notification["unfurl_links"] is False
    assert notification["unfurl_media"] is False


def test_scheduled_reminder_does_not_raise_if_admin_notification_also_fails(
    monkeypatch,
):
    dependencies = fake_dependencies()
    reminder = MagicMock()
    reminder.return_value.run.side_effect = RuntimeError("reminder failed")
    dependencies.create_web_client.return_value.chat_postMessage.side_effect = (
        RuntimeError("Slack failed")
    )
    monkeypatch.setattr(jobs, "RemindBigchat", reminder)
    jobs.remind_bigchat(dependencies)
