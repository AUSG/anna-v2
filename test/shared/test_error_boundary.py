import unittest

from shared.error_boundary import USER_NOTICE, report_failure
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_channel_created_event,
    create_sample_reaction_added_event,
)

ADMIN_CHANNEL = "C_ADMIN"


class TestReportFailure(unittest.TestCase):
    def test_admin_gets_full_report_and_requester_gets_notice_in_thread(self):
        slack = fake_slack()
        event = {"channel": "C03SZTDEDK3", "ts": "1689437594.220999", "text": "q) 안녕"}

        report_failure(slack, ADMIN_CHANNEL, event, RuntimeError("boom"))

        slack.send_channel_message.assert_called_once()
        admin_channel, report = slack.send_channel_message.call_args.args
        assert admin_channel == ADMIN_CHANNEL
        assert "예상치 못한 에러가 발생했어" in report
        assert "q) 안녕" in report  # event
        assert "boom" in report  # exception
        assert "RuntimeError" in report  # traceback
        slack.send_thread_message.assert_called_once_with(
            "C03SZTDEDK3", "1689437594.220999", USER_NOTICE
        )

    def test_report_includes_traceback_of_raised_exception(self):
        slack = fake_slack()

        def boom():
            raise ValueError("본 작업 실패")

        try:
            boom()
        except ValueError as ex:
            report_failure(slack, ADMIN_CHANNEL, {}, ex)

        report = slack.send_channel_message.call_args_list[0].args[1]
        assert "in boom" in report
        assert "본 작업 실패" in report

    def test_app_mention_event_is_answered_on_its_own_message(self):
        slack = fake_slack()
        event = create_sample_app_mention_event("<@UANNA> 안녕")

        report_failure(slack, ADMIN_CHANNEL, event, RuntimeError("boom"))

        # thread_ts 가 아니라 멘션한 글 자신(ts)에 답한다
        slack.send_thread_message.assert_called_once_with(
            event["channel"], event["ts"], USER_NOTICE
        )

    def test_reaction_event_is_answered_on_the_reacted_message(self):
        slack = fake_slack()
        event = create_sample_reaction_added_event("gogo")

        report_failure(slack, ADMIN_CHANNEL, event, RuntimeError("boom"))

        slack.send_thread_message.assert_called_once_with(
            event["item"]["channel"], event["item"]["ts"], USER_NOTICE
        )

    def test_channel_created_event_is_answered_in_the_new_channel(self):
        slack = fake_slack()
        event = create_sample_channel_created_event("C_NEW")

        report_failure(slack, ADMIN_CHANNEL, event, RuntimeError("boom"))

        # 답글을 달 ts 가 없으니 채널 자체에 안내한다
        slack.send_thread_message.assert_not_called()
        assert slack.send_channel_message.call_count == 2
        assert slack.send_channel_message.call_args_list[1].args == (
            "C_NEW",
            USER_NOTICE,
        )

    def test_falls_back_to_admin_channel_when_event_has_no_target(self):
        slack = fake_slack()

        report_failure(slack, ADMIN_CHANNEL, {}, RuntimeError("boom"))

        slack.send_thread_message.assert_not_called()
        assert [c.args[0] for c in slack.send_channel_message.call_args_list] == [
            ADMIN_CHANNEL,
            ADMIN_CHANNEL,
        ]
        assert slack.send_channel_message.call_args_list[1].args[1] == USER_NOTICE
