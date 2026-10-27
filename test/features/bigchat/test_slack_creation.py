import unittest
from unittest.mock import call

from slack_sdk.errors import SlackApiError

from features.bigchat.presentation.messages import (
    bigchat_created_message,
    invalid_bigchat_name_message,
)
from features.bigchat.services.commands import CreateBigchat
from features.bigchat.slack import create_from_mention
from shared.slack_events import MentionEvent
from test.fixtures.runtime import fake_runtime
from test.fixtures.slack_events import create_sample_app_mention_event

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid=161837744"


class TestCreateFromMention(unittest.TestCase):
    def setUp(self):
        self.runtime = fake_runtime()
        self.slack = self.runtime.slack
        self.sheets = self.runtime.sheets()
        self.members = self.runtime.members()
        self.slack.get_reaction.return_value = None  # 미리 눌린 이모지 없음
        self.sheets.create_bigchat_sheet.return_value = 161837744
        self.sheets.get_url.return_value = SHEET_URL

    def run_sut(self, sheet_name, event_dict):
        return create_from_mention(
            CreateBigchat(sheet_name),
            MentionEvent.from_payload(event_dict),
            self.slack,
            self.runtime,
        )

    def test_run(self):
        event = create_sample_app_mention_event(f"<@U01BN035Y6L> 새로운 빅챗 {SHEET_NAME}")

        result = self.run_sut(SHEET_NAME, event)

        assert result is True
        assert self.sheets.mock_calls == [
            call.create_bigchat_sheet(SHEET_NAME),
            call.get_url(161837744),
        ]
        self.slack.send_thread_message.assert_called_once_with(
            event["channel"],
            event["ts"],
            bigchat_created_message(SHEET_URL, SHEET_NAME),
        )
        assert (
            self.slack.send_thread_message.call_args.args[2]
            == f"새로운 빅챗, 등록 완료! <{SHEET_URL}|{SHEET_NAME}> :google_spreadsheets:"
        )
        # 링크를 올린 '뒤에' 모집글(스레드 부모)의 reaction 을 읽어야 그 사이에 눌린
        # reaction 이 join_bigchat 과 일괄 등록 중 어느 한쪽에는 반드시 잡힌다
        call_names = [name for name, _, _ in self.slack.mock_calls]
        assert call_names.index("send_thread_message") < call_names.index(
            "get_reaction"
        )
        self.slack.get_reaction.assert_called_once_with(
            event["channel"], event["thread_ts"], "gogo"
        )
        assert self.members.mock_calls == []

    def test_reads_reactions_from_mention_itself_when_not_in_thread(self):
        event = create_sample_app_mention_event(f"<@U01BN035Y6L> 새로운 빅챗 {SHEET_NAME}")
        del event["thread_ts"]
        del event["parent_user_id"]

        assert self.run_sut(SHEET_NAME, event)

        self.slack.get_reaction.assert_called_once_with(
            event["channel"], event["ts"], "gogo"
        )

    def test_rejected_by_invalid_format(self):
        for sheet_name in [
            "",  # 이름 없음
            "빅챗 23-07-31",  # 시간 없음 (구형식)
            "AI 밋업 26-02-30 19:00~21:00",  # 존재하지 않는 날짜
            "AI 밋업 26-08-20 21:00~19:00",  # 종료가 시작보다 빠름
        ]:
            with self.subTest(sheet_name=sheet_name):
                self.setUp()
                event = create_sample_app_mention_event(
                    f"<@U01BN035Y6L> 새로운 빅챗 {sheet_name}"
                )

                result = self.run_sut(sheet_name, event)

                assert result is False
                assert self.sheets.mock_calls == []
                assert self.slack.mock_calls == [
                    call.send_ephemeral(
                        event["channel"],
                        event["user"],
                        invalid_bigchat_name_message(event["user"]),
                        ts=event["ts"],
                    )
                ]
                notice = self.slack.send_ephemeral.call_args.args[2]
                assert notice == (
                    f"<@{event['user']}> 형식이 올바르지 않아서 빅챗을 만들지 않았어. "
                    "아래 형식으로 다시 입력해줘!\n"
                    "`새로운 빅챗 <이름> yy-MM-DD HH:mm~HH:mm`\n"
                    "예) `새로운 빅챗 AI 밋업 26-08-20 19:00~21:00`\n"
                    "(실제 존재하는 날짜/시각이어야 하고, 종료 시각은 시작보다 늦어야 해!)"
                )

    def test_invalid_notice_failure_does_not_keep_validation_error_context(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 nope")
        for failure in (
            RuntimeError("안내 전송 실패"),
            SlackApiError("안내 전송 실패", {"error": "channel_not_found"}),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.setUp()
                self.slack.send_ephemeral.side_effect = failure

                with self.assertRaises(type(failure)) as error:
                    self.run_sut("nope", event)

                assert error.exception is failure
                assert failure.__context__ is None
                assert failure.__cause__ is None
                self.slack.send_ephemeral.assert_called_once()
                self.slack.send_thread_message.assert_not_called()
                self.slack.get_reaction.assert_not_called()
                assert self.sheets.mock_calls == []
                assert self.members.mock_calls == []

    def test_url_failure_is_propagated_without_publishing_or_backfilling(self):
        event = create_sample_app_mention_event(f"<@U01BN035Y6L> 새로운 빅챗 {SHEET_NAME}")
        failure = RuntimeError("URL 조회 실패")
        self.sheets.get_url.side_effect = failure

        with self.assertRaises(RuntimeError) as error:
            self.run_sut(SHEET_NAME, event)

        assert error.exception is failure
        assert self.sheets.mock_calls == [
            call.create_bigchat_sheet(SHEET_NAME),
            call.get_url(161837744),
        ]
        assert self.slack.mock_calls == []
        assert self.members.mock_calls == []
