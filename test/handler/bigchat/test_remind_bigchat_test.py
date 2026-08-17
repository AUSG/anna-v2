import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from handler.bigchat.remind_bigchat import ReminderResult
from handler.bigchat.remind_bigchat_test import RemindBigchatTest

ANNA_ID = "UANNA"


def _event(text):
    return {
        "text": text,
        "ts": "1689403771.805849",
        "channel": "C03SZTDEDK3",
        "user": "U01BN035Y6L",
    }


class TestRemindBigchatTest(unittest.TestCase):
    def _build_sut(self, text):
        self.mock_slack_client = MagicMock()
        return RemindBigchatTest(
            _event(text),
            self.mock_slack_client,
            MagicMock(),
            MagicMock(),
            ANNA_ID,
        )

    def test_can_handle(self):
        assert self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001>").can_handle()
        assert not self._build_sut(f"<@{ANNA_ID}> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00").can_handle()
        assert not self._build_sut(f"<@{ANNA_ID}> 안녕").can_handle()

    def test_runs_reminder_for_mentioned_users_only(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001> <@U0002>")

        with patch(
            "handler.bigchat.remind_bigchat_test.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = ReminderResult(
                target_date=date(2026, 8, 20),
                bigchat_names=["AI 밋업"],
                applicant_cnt=5,
                resolved_cnt=4,
                sent_cnt=2,
            )
            result = sut.handle_mention()

        assert result is True
        # 안나 자신은 대상에서 빠지고, 멘션된 사람만 간다
        assert mock_reminder.return_value.run.call_args.kwargs["only_user_ids"] == [
            "U0001",
            "U0002",
        ]
        report = self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
            "msg"
        ]
        assert "<@U0001>" in report and "<@U0002>" in report
        assert "5명" in report and "4명" in report  # 실제 발송이었다면 어땠을지도 알려준다

    def test_refuses_without_a_target(self):
        """대상 없이 실행하면 아무에게도 보내지 않는다 (신청자 전원 오발송 방지)."""
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트")

        with patch(
            "handler.bigchat.remind_bigchat_test.RemindBigchat"
        ) as mock_reminder:
            result = sut.handle_mention()

        assert result is False
        mock_reminder.return_value.run.assert_not_called()
        msg = self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
            "msg"
        ]
        assert "받을 사람을 같이 멘션해줘" in msg

    def test_reports_when_no_bigchat_tomorrow(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001>")

        with patch(
            "handler.bigchat.remind_bigchat_test.RemindBigchat"
        ) as mock_reminder:
            mock_reminder.return_value.run.return_value = ReminderResult(
                target_date=date(2026, 8, 20),
                bigchat_names=[],
                parsed_sheet_cnt=3,
                ignored_sheet_cnt=7,
            )
            sut.handle_mention()

        msg = self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
            "msg"
        ]
        assert "못 찾았어" in msg
        assert "3개" in msg and "7개" in msg  # 시트 형식 문제인지 바로 판단할 수 있게
