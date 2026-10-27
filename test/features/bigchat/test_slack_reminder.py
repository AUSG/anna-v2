import unittest
from datetime import date
from unittest.mock import patch

from features.bigchat.models import ReminderResult
from features.bigchat.presentation.reminders import (
    USAGE,
    build_report,
    missing_targets_message,
)
from features.bigchat.services.commands import Reminder
from features.bigchat.slack import remind_now
from shared.slack_events import MentionEvent
from test.fixtures.runtime import fake_runtime

ANNA_ID = "UANNA"
EVENT = MentionEvent(
    text="", ts="1689403771.805849", channel="C03SZTDEDK3", user="U01BN035Y6L"
)


def _result(**kwargs):
    return ReminderResult(target_date=date(2026, 8, 20), **kwargs)


class RemindNowTestBase(unittest.TestCase):
    def setUp(self):
        self.runtime = fake_runtime(ANNA_ID=ANNA_ID)
        self.slack = self.runtime.slack
        patcher = patch("features.bigchat.slack.RemindBigchat", autospec=True)
        self.reminder = patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, command):
        return remind_now(command, EVENT, self.slack, self.runtime)

    def _reply(self):
        self.slack.send_ephemeral.assert_called_once()
        args, kwargs = self.slack.send_ephemeral.call_args
        assert args[:2] == (EVENT.channel, EVENT.user)
        assert kwargs == {"ts": EVENT.ts}
        return args[2]


class TestUsage(RemindNowTestBase):
    def test_shows_usage_without_a_mode(self):
        result = self._run(Reminder("usage"))

        assert result is False
        self.reminder.assert_not_called()
        self.reminder.return_value.run.assert_not_called()
        assert self._reply() == USAGE
        assert "지금 전원 발송" in self._reply()


class TestTestMode(RemindNowTestBase):
    def test_runs_reminder_for_mentioned_users_only(self):
        self.reminder.return_value.run.return_value = _result(
            bigchat_names=["AI 밋업"], applicant_cnt=5, resolved_cnt=4, sent_cnt=2
        )

        result = self._run(Reminder("test", ("U0001", "U0002")))

        assert result is True
        self.reminder.assert_called_once_with(
            self.slack, self.runtime.sheets(), self.runtime.members()
        )
        self.reminder.return_value.run.assert_called_once_with(
            only_user_ids=["U0001", "U0002"]
        )
        report = self._reply()
        assert "<@U0001>" in report and "<@U0002>" in report
        assert "5명" in report and "4명" in report  # 실제 발송이었다면 어땠을지도 알려준다

    def test_refuses_without_a_target(self):
        """대상 없이 테스트하면 아무에게도 보내지 않는다 (신청자 전원 오발송 방지)."""
        result = self._run(Reminder("test", ()))

        assert result is False
        self.reminder.assert_not_called()
        self.reminder.return_value.run.assert_not_called()
        reply = self._reply()
        assert reply == missing_targets_message(EVENT.user)
        assert reply == (
            "받을 사람을 같이 멘션해줘! 실수로 신청자 전원에게 나가지 않게 대상 지정을 필수로 해뒀어.\n"
            "예) `빅챗 리마인더 테스트 <@U01BN035Y6L>`\n"
            "(진짜로 전원에게 보내려면 `빅챗 리마인더 지금 전원 발송` 라고 해줘!)"
        )
        self.slack.send_direct_message.assert_not_called()

    def test_reports_when_no_bigchat_tomorrow(self):
        self.reminder.return_value.run.return_value = _result(
            bigchat_names=[], parsed_sheet_cnt=3, ignored_sheet_cnt=7
        )

        self._run(Reminder("test", ("U0001",)))

        report = self._reply()
        assert "못 찾았어" in report
        assert "3개" in report and "7개" in report  # 시트 형식 문제인지 바로 판단할 수 있게


class TestBroadcastMode(RemindNowTestBase):
    def test_sends_to_every_applicant(self):
        self.reminder.return_value.run.return_value = _result(
            bigchat_names=["빅챗"], applicant_cnt=31, resolved_cnt=31, sent_cnt=31
        )

        with self.assertLogs("features.bigchat.slack", level="WARNING") as logs:
            result = self._run(Reminder("broadcast"))

        assert result is True
        # 대상 제한 없이 실제 신청자에게 나가야 한다
        self.reminder.assert_called_once_with(
            self.slack, self.runtime.sheets(), self.runtime.members()
        )
        self.reminder.return_value.run.assert_called_once_with()
        report = self._reply()
        assert "31명" in report
        assert len(logs.records) == 1
        assert logs.records[0].name == "features.bigchat.slack"

    def test_reports_unresolved_applicants(self):
        self.reminder.return_value.run.return_value = _result(
            bigchat_names=["빅챗"], applicant_cnt=31, resolved_cnt=28, sent_cnt=28
        )

        self._run(Reminder("broadcast"))

        assert "3명은 멤버 시트에서 슬랙 계정을 못 찾아서" in self._reply()


class TestReminderBoundaries(RemindNowTestBase):
    def test_run_error_propagates_without_result_reply(self):
        self.reminder.return_value.run.side_effect = RuntimeError("sheet unavailable")

        with self.assertRaisesRegex(RuntimeError, "sheet unavailable"):
            self._run(Reminder("test", ("U1",)))

        self.slack.send_ephemeral.assert_not_called()

    def test_reply_error_is_not_treated_as_a_failed_dm(self):
        self.slack.send_ephemeral.side_effect = RuntimeError("reply failed")
        self.reminder.return_value.run.return_value = _result(
            bigchat_names=["빅챗"], sent_cnt=1
        )

        with self.assertRaisesRegex(RuntimeError, "reply failed"):
            self._run(Reminder("test", ("U1",)))

        self.reminder.return_value.run.assert_called_once_with(only_user_ids=["U1"])

    def test_report_keeps_original_unresolved_note_indentation(self):
        result = _result(
            bigchat_names=["빅챗"], applicant_cnt=2, resolved_cnt=1, sent_cnt=1
        )
        assert build_report(result, None) == (
            "                2026-08-20 빅챗 `빅챗` 신청자들에게 리마인더를 보냈어!\n"
            "                - 신청 시트에서 찾은 신청자: 2명\n"
            "                - 실제로 DM 을 보낸 사람: 1명\n"
            "신청자 1명은 멤버 시트에서 슬랙 계정을 못 찾아서 못 보냈어. (누군지는 로그에 남겼어!)"
        )
