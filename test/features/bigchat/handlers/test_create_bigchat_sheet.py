import unittest
from unittest.mock import MagicMock, call

from slack_sdk.errors import SlackApiError

from features.bigchat.handlers.create_bigchat_sheet import CreateBigchatSheet
from test.fixtures.slack_events import create_sample_app_mention_event

MENTION = "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"


class TestCreateBigchatSheet(unittest.TestCase):
    def setUp(self):
        self.mock_slack_client = MagicMock()
        self.mock_slack_client.get_emoji.return_value = None  # 미리 눌린 이모지 없음
        self.mock_gs_client = MagicMock()
        self.mock_gs_client.create_bigchat_sheet.return_value = 161837744
        self.mock_gs_client.get_url.return_value = (
            "https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid=161837744"
        )
        self.mock_member_manager = MagicMock()

    def create_sut(self, event):
        return CreateBigchatSheet(
            event,
            self.mock_slack_client,
            self.mock_gs_client,
            self.mock_member_manager,
            "gogo",
        )

    def test_run(self):
        event = create_sample_app_mention_event(MENTION)

        result = self.create_sut(event).handle_mention()

        assert result is True
        assert self.mock_gs_client.mock_calls == [
            call.create_bigchat_sheet("AI 밋업 26-08-20 19:00~21:00"),
            call.get_url(161837744),
        ]
        self.mock_slack_client.send_message.assert_called_once_with(
            msg=(
                "새로운 빅챗, 등록 완료! "
                "<https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid=161837744|"
                "AI 밋업 26-08-20 19:00~21:00> :google_spreadsheets:"
            ),
            ts=event["ts"],
        )
        # 링크를 올린 '뒤에' 모집글(스레드 부모)의 reaction 을 읽어야 그 사이에 눌린
        # reaction 이 JoinBigchat 과 일괄 등록 중 어느 한쪽에는 반드시 잡힌다
        call_names = [name for name, _, _ in self.mock_slack_client.mock_calls]
        assert call_names.index("send_message") < call_names.index("get_emoji")
        self.mock_slack_client.get_emoji.assert_called_once_with(
            channel=event["channel"], ts=event["thread_ts"], emoji_name="gogo"
        )

    def test_reads_reactions_from_mention_itself_when_not_in_thread(self):
        event = create_sample_app_mention_event(MENTION)
        del event["thread_ts"]
        del event["parent_user_id"]

        assert self.create_sut(event).handle_mention()

        self.mock_slack_client.get_emoji.assert_called_once_with(
            channel=event["channel"], ts=event["ts"], emoji_name="gogo"
        )

    def test_not_run_by_command_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>빅챗 23-07-31")

        result = self.create_sut(event).handle_mention()

        assert result is False
        assert self.mock_gs_client.mock_calls == []
        assert self.mock_slack_client.mock_calls == []

    def test_rejected_by_invalid_format(self):
        for text in [
            "<@U01BN035Y6L> 새로운 빅챗 \n\n\n\n",  # 이름 없음
            "<@U01BN035Y6L> 새로운 빅챗 빅챗 23-07-31",  # 시간 없음 (구형식)
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-02-30 19:00~21:00",  # 존재하지 않는 날짜
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 21:00~19:00",  # 종료가 시작보다 빠름
            MENTION + " <@UOTHER>",  # 날짜/시각 뒤에 다른 입력이 붙은 경우
        ]:
            with self.subTest(text=text):
                self.setUp()
                event = create_sample_app_mention_event(text)

                result = self.create_sut(event).handle_mention()

                assert result is False
                assert self.mock_gs_client.mock_calls == []
                assert self.mock_slack_client.mock_calls == [
                    call.send_message_only_visible_to_user(
                        msg=(
                            f"<@{event['user']}> 형식이 올바르지 않아서 빅챗을 만들지 않았어. "
                            "아래 형식으로 다시 입력해줘!\n"
                            "`새로운 빅챗 <이름> yy-MM-DD HH:mm~HH:mm`\n"
                            "예) `새로운 빅챗 AI 밋업 26-08-20 19:00~21:00`\n"
                            "(실제 존재하는 날짜/시각이어야 하고, 종료 시각은 시작보다 늦어야 해!)"
                        ),
                        channel=event["channel"],
                        ts=event["ts"],
                        user_id=event["user"],
                    )
                ]

    def test_invalid_notice_failure_does_not_create_a_sheet(self):
        for failure in (
            RuntimeError("안내 전송 실패"),
            SlackApiError("안내 전송 실패", {"error": "channel_not_found"}),
        ):
            with self.subTest(failure=type(failure).__name__):
                self.setUp()
                event = create_sample_app_mention_event(
                    "<@U01BN035Y6L> 새로운 빅챗 nope"
                )
                self.mock_slack_client.send_message_only_visible_to_user.side_effect = (
                    failure
                )

                with self.assertRaises(type(failure)) as error:
                    self.create_sut(event).handle_mention()

                assert error.exception is failure
                self.mock_slack_client.send_message_only_visible_to_user.assert_called_once()
                self.mock_slack_client.send_message.assert_not_called()
                self.mock_slack_client.get_emoji.assert_not_called()
                assert self.mock_gs_client.mock_calls == []
                assert self.mock_member_manager.mock_calls == []

    def test_url_failure_is_propagated_without_publishing_or_backfilling(self):
        event = create_sample_app_mention_event(MENTION)
        failure = RuntimeError("URL 조회 실패")
        self.mock_gs_client.get_url.side_effect = failure

        with self.assertRaises(RuntimeError) as error:
            self.create_sut(event).handle_mention()

        assert error.exception is failure
        assert self.mock_gs_client.mock_calls == [
            call.create_bigchat_sheet("AI 밋업 26-08-20 19:00~21:00"),
            call.get_url(161837744),
        ]
        assert self.mock_slack_client.mock_calls == []
        assert self.mock_member_manager.mock_calls == []

    def test_success_notice_failure_does_not_recreate_or_backfill(self):
        event = create_sample_app_mention_event(MENTION)
        failure = SlackApiError("안내 전송 실패", {"error": "ratelimited"})
        self.mock_slack_client.send_message.side_effect = failure

        with self.assertRaises(SlackApiError) as error:
            self.create_sut(event).handle_mention()

        assert error.exception is failure
        self.mock_gs_client.create_bigchat_sheet.assert_called_once_with(
            "AI 밋업 26-08-20 19:00~21:00"
        )
        self.mock_slack_client.send_message.assert_called_once()
        self.mock_slack_client.send_message_only_visible_to_user.assert_not_called()
        self.mock_slack_client.get_emoji.assert_not_called()
        assert self.mock_member_manager.mock_calls == []

    def test_ignores_description_after_first_line(self):
        event = create_sample_app_mention_event(MENTION + "\n이번 빅챗 소개글입니다")

        assert self.create_sut(event).handle_mention() is True

        self.mock_gs_client.create_bigchat_sheet.assert_called_once_with(
            "AI 밋업 26-08-20 19:00~21:00"
        )
