import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from handler.bigchat.remind_bigchat import ReminderResult
from handler.bigchat.remind_bigchat_command import RemindBigchatCommand

ANNA_ID = "UANNA"


def _event(text):
    return {
        "text": text,
        "ts": "1689403771.805849",
        "channel": "C03SZTDEDK3",
        "user": "U01BN035Y6L",
    }


def _result(**kwargs):
    return ReminderResult(target_date=date(2026, 8, 20), **kwargs)


class RemindBigchatCommandTestBase(unittest.TestCase):
    def _build_sut(self, text):
        self.mock_slack_client = MagicMock()
        return RemindBigchatCommand(
            _event(text), self.mock_slack_client, MagicMock(), MagicMock(), ANNA_ID
        )

    def _reply(self):
        return (
            self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "msg"
            ]
        )


class TestCanHandle(RemindBigchatCommandTestBase):
    def test_can_handle(self):
        assert self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001>").can_handle()
        assert self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송").can_handle()
        assert not self._build_sut(
            f"<@{ANNA_ID}> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        ).can_handle()
        assert not self._build_sut(f"<@{ANNA_ID}> 안녕").can_handle()

    def test_shows_usage_without_a_mode(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            result = sut.handle_mention()

        assert result is False
        mock_reminder.return_value.run.assert_not_called()
        assert "지금 전원 발송" in self._reply()


class TestTestMode(RemindBigchatCommandTestBase):
    def test_runs_reminder_for_mentioned_users_only(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001> <@U0002>")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = _result(
                bigchat_names=["AI 밋업"], applicant_cnt=5, resolved_cnt=4, sent_cnt=2
            )
            result = sut.handle_mention()

        assert result is True
        # 안나 자신은 대상에서 빠지고, 멘션된 사람만 간다
        assert mock_reminder.return_value.run.call_args.kwargs["only_user_ids"] == [
            "U0001",
            "U0002",
        ]
        report = self._reply()
        assert "<@U0001>" in report and "<@U0002>" in report
        assert "5명" in report and "4명" in report  # 실제 발송이었다면 어땠을지도 알려준다

    def test_refuses_without_a_target(self):
        """대상 없이 테스트하면 아무에게도 보내지 않는다 (신청자 전원 오발송 방지)."""
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            result = sut.handle_mention()

        assert result is False
        mock_reminder.assert_not_called()
        mock_reminder.return_value.run.assert_not_called()
        reply = self._reply()
        assert "받을 사람을 같이 멘션해줘" in reply
        self.mock_slack_client.send_message_only_visible_to_user.assert_called_once_with(
            msg=reply,
            channel="C03SZTDEDK3",
            ts="1689403771.805849",
            user_id="U01BN035Y6L",
        )
        self.mock_slack_client.send_direct_message.assert_not_called()

    def test_reports_when_no_bigchat_tomorrow(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001>")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = _result(
                bigchat_names=[], parsed_sheet_cnt=3, ignored_sheet_cnt=7
            )
            sut.handle_mention()

        report = self._reply()
        assert "못 찾았어" in report
        assert "3개" in report and "7개" in report  # 시트 형식 문제인지 바로 판단할 수 있게


class TestBroadcastMode(RemindBigchatCommandTestBase):
    def test_sends_to_every_applicant(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = _result(
                bigchat_names=["빅챗"], applicant_cnt=31, resolved_cnt=31, sent_cnt=31
            )
            result = sut.handle_mention()

        assert result is True
        # 대상 제한 없이(only_user_ids=None) 실제 신청자에게 나가야 한다
        assert mock_reminder.return_value.run.call_args.kwargs["only_user_ids"] is None
        report = self._reply()
        assert "31명" in report

    def test_broadcast_ignores_mentioned_users(self):
        """전원 발송에 사람을 같이 멘션해도 전원 발송이다 (문구가 명시적이라 그게 의도)."""
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송 <@U0001>")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = _result(
                bigchat_names=["빅챗"], applicant_cnt=3, resolved_cnt=3, sent_cnt=3
            )
            sut.handle_mention()

        assert mock_reminder.return_value.run.call_args.kwargs["only_user_ids"] is None

    def test_reports_unresolved_applicants(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = _result(
                bigchat_names=["빅챗"], applicant_cnt=31, resolved_cnt=28, sent_cnt=28
            )
            sut.handle_mention()

        assert "3명은 멤버 시트에서 슬랙 계정을 못 찾아서" in self._reply()

    def test_partial_phrase_does_not_broadcast(self):
        """'전원 발송' 만으로는 안 되고 문구를 통째로 쳐야 한다."""
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 전원 발송")

        with patch(
            "handler.bigchat.remind_bigchat_command.RemindBigchat"
        ) as mock_reminder:
            result = sut.handle_mention()

        assert result is False
        mock_reminder.return_value.run.assert_not_called()


class TestReminderCommandBoundaries(RemindBigchatCommandTestBase):
    def test_unrelated_mention_has_no_reply_or_run(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 안녕")
        with patch("handler.bigchat.remind_bigchat_command.RemindBigchat") as reminder:
            assert sut.handle_mention() is False
        reminder.assert_not_called()
        self.mock_slack_client.send_message_only_visible_to_user.assert_not_called()

    def test_target_helper_keeps_duplicates_and_invoker(self):
        for text, expected in [
            (
                f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U1><@U1> <@U01BN035Y6L> <@{ANNA_ID}> <@lower>",
                ["U1", "U1", "U01BN035Y6L"],
            ),
            (
                "<@UANNA> 테스트 <@U1><@U1> <@UINVOKER> <@UANNA> <@lower> <@U_2> <@U3|이름> <@A9>",
                ["U1", "U1", "UINVOKER", "A9"],
            ),
        ]:
            with self.subTest(text=text):
                assert self._build_sut(text)._target_user_ids() == expected

    def test_broadcast_takes_precedence_over_test_phrase(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 지금 전원 발송 <@U1>")
        with patch("handler.bigchat.remind_bigchat_command.RemindBigchat") as reminder:
            reminder.return_value.run.return_value = _result(bigchat_names=["빅챗"])
            with self.assertLogs(
                "handler.bigchat.remind_bigchat_command", level="WARNING"
            ) as logs:
                assert sut.handle_mention() is True
        reminder.return_value.run.assert_called_once_with(only_user_ids=None)
        assert len(logs.records) == 1
        assert logs.records[0].name == "handler.bigchat.remind_bigchat_command"

    def test_run_helper_uses_shared_reminder_and_original_clients(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더")
        expected = _result()
        with patch("handler.bigchat.remind_bigchat_command.RemindBigchat") as reminder:
            reminder.return_value.run.return_value = expected
            assert sut._run(only_user_ids=[]) is expected
        reminder.assert_called_once_with(
            sut.slack_client, sut.gs_client, sut.member_manager
        )
        reminder.return_value.run.assert_called_once_with(only_user_ids=[])

    def test_run_error_propagates_without_result_reply(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U1>")
        with patch("handler.bigchat.remind_bigchat_command.RemindBigchat") as reminder:
            reminder.return_value.run.side_effect = RuntimeError("sheet unavailable")
            with self.assertRaisesRegex(RuntimeError, "sheet unavailable"):
                sut.handle_mention()
        self.mock_slack_client.send_message_only_visible_to_user.assert_not_called()

    def test_reply_error_is_not_treated_as_a_failed_dm(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U1>")
        self.mock_slack_client.send_message_only_visible_to_user.side_effect = (
            RuntimeError("reply failed")
        )
        with patch("handler.bigchat.remind_bigchat_command.RemindBigchat") as reminder:
            reminder.return_value.run.return_value = _result(
                bigchat_names=["빅챗"], sent_cnt=1
            )
            with self.assertRaisesRegex(RuntimeError, "reply failed"):
                sut.handle_mention()
        reminder.return_value.run.assert_called_once_with(only_user_ids=["U1"])
