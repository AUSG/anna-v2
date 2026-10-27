import json
import unittest
from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from features.bigchat.models import InvalidBigchatName
from features.bigchat.slack import (
    CREATE_BIGCHAT_VIEW_ID,
    DATE_BLOCK,
    END_BLOCK,
    NAME_BLOCK,
    START_BLOCK,
    OpenCreateBigchatModal,
    SubmitCreateBigchatModal,
    normalize_shortcut_body,
    normalize_view_body,
)
from features.bigchat.services.sheet_link import SPREADSHEET_PAT
from test.fixtures.slack_events import (
    create_sample_message_shortcut_body,
    create_sample_view_submission_body,
)


class TestNormalizeBodies(unittest.TestCase):
    def test_shortcut_on_plain_message(self):
        body = create_sample_message_shortcut_body()

        event = normalize_shortcut_body(body)

        assert event["channel"] == "C03SZTDEDK3"
        assert event["ts"] == "1688801145.307229"
        assert event["user"] == "UQJ8HQJG5"

    def test_shortcut_on_thread_reply_anchors_to_thread_root(self):
        body = create_sample_message_shortcut_body(thread_ts="1688800000.000001")

        event = normalize_shortcut_body(body)

        assert event["ts"] == "1688800000.000001"

    def test_view_submission(self):
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )

        event = normalize_view_body(body)

        assert event["channel"] == "C03SZTDEDK3"
        assert event["ts"] == "1688801145.307229"
        assert event["user"] == "UQJ8HQJG5"


class TestOpenCreateBigchatModal(unittest.TestCase):
    def test_run(self):
        event = normalize_shortcut_body(create_sample_message_shortcut_body())
        mock_web_client = MagicMock()
        sut = OpenCreateBigchatModal(event, mock_web_client)

        result = sut.run()

        assert result is True
        mock_web_client.views_open.assert_called_once()
        kwargs = mock_web_client.views_open.call_args.kwargs
        assert kwargs["trigger_id"] == event["trigger_id"]

        view = kwargs["view"]
        assert view["callback_id"] == CREATE_BIGCHAT_VIEW_ID
        assert [block["block_id"] for block in view["blocks"]] == [
            NAME_BLOCK,
            DATE_BLOCK,
            START_BLOCK,
            END_BLOCK,
        ]
        assert [block["element"]["type"] for block in view["blocks"]] == [
            "plain_text_input",
            "datepicker",
            "timepicker",
            "timepicker",
        ]

        # 제출 시점에 스레드 답글을 달 수 있어야 하므로 실행 컨텍스트가 실려 있어야 한다
        metadata = json.loads(view["private_metadata"])
        assert metadata["channel"] == "C03SZTDEDK3"
        assert metadata["thread_ts"] == "1688801145.307229"
        assert metadata["response_url"] == event["response_url"]


class TestSubmitCreateBigchatModal(unittest.TestCase):
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid=987654321"

    def _build_sut(self, name="AI 밋업", date="2026-08-20", start="19:00", end="21:00"):
        body = create_sample_view_submission_body(name, date, start, end)
        event = normalize_view_body(body)
        mock_ack = MagicMock()
        mock_slack_client = MagicMock()
        mock_slack_client.get_emoji.return_value = None  # 미리 눌린 이모지 없음
        mock_gs_client = MagicMock()
        mock_gs_client.create_bigchat_sheet.return_value = 987654321
        mock_gs_client.get_url.return_value = self.SHEET_URL
        self.mock_member_manager = MagicMock()
        sut = SubmitCreateBigchatModal(
            event,
            mock_ack,
            mock_slack_client,
            mock_gs_client,
            self.mock_member_manager,
            "gogo",
        )
        return sut, mock_ack, mock_slack_client, mock_gs_client

    def test_run(self):
        sut, mock_ack, mock_slack_client, mock_gs_client = self._build_sut()

        result = sut.run()

        assert result is True
        mock_ack.assert_called_once_with()
        mock_gs_client.create_bigchat_sheet.assert_called_once_with(
            "AI 밋업 26-08-20 19:00~21:00"
        )
        mock_slack_client.send_thread_message.assert_called_once_with(
            msg=(
                f"새로운 빅챗, 등록 완료! <{self.SHEET_URL}|"
                "AI 밋업 26-08-20 19:00~21:00> :google_spreadsheets:"
            ),
            channel="C03SZTDEDK3",
            ts="1688801145.307229",
        )
        # :gogo: 참여 흐름(JoinBigchat)이 이 답글에서 시트 gid를 찾아낼 수 있어야 한다
        msg = mock_slack_client.send_thread_message.call_args.kwargs["msg"]
        assert SPREADSHEET_PAT.search(msg).groups()[0] == "987654321"
        # 링크를 올린 뒤, 모달을 띄운 메시지가 속한 스레드의 첫 글(모집글)에서 reaction 을 읽는다
        call_names = [name for name, _, _ in mock_slack_client.mock_calls]
        assert call_names.index("send_thread_message") < call_names.index("get_emoji")
        mock_slack_client.get_emoji.assert_called_once_with(
            channel="C03SZTDEDK3", ts="1688801145.307229", emoji_name="gogo"
        )

    def test_rejected_by_invalid_fields(self):
        cases = [
            ({"start": "21:00", "end": "19:00"}, {END_BLOCK: "종료 시각은 시작 시각보다 늦어야 해!"}),
            ({"start": "19:00", "end": "19:00"}, {END_BLOCK: "종료 시각은 시작 시각보다 늦어야 해!"}),
            ({"name": "   "}, {NAME_BLOCK: "이름을 입력해줘!"}),
            # 위젯이 형식을 보장하지만, 존재하지 않는 날짜는 방어적으로 거른다
            ({"date": "2026-02-30"}, {NAME_BLOCK: "형식이 올바르지 않아. 입력값을 다시 확인해줘!"}),
            # 필드 오류가 있으면 형식 오류는 덧붙이지 않는다
            (
                {"name": "   ", "start": "21:00", "end": "19:00"},
                {
                    NAME_BLOCK: "이름을 입력해줘!",
                    END_BLOCK: "종료 시각은 시작 시각보다 늦어야 해!",
                },
            ),
        ]
        for overrides, expected in cases:
            with self.subTest(**overrides):
                sut, mock_ack, mock_slack_client, mock_gs_client = self._build_sut(
                    **overrides
                )

                assert sut.run() is False

                mock_ack.assert_called_once_with(
                    response_action="errors", errors=expected
                )
                assert mock_gs_client.mock_calls == []
                assert mock_slack_client.mock_calls == []

    def test_ack_failure_does_not_create_a_sheet(self):
        for date in ("2026-08-20", "2026-02-30"):
            with self.subTest(date=date):
                sut, mock_ack, mock_slack_client, mock_gs_client = self._build_sut(
                    date=date
                )
                failure = RuntimeError("ACK 실패")
                mock_ack.side_effect = failure

                with self.assertRaises(RuntimeError) as error:
                    sut.run()

                assert error.exception is failure
                assert failure.__context__ is None
                mock_ack.assert_called_once()
                assert mock_gs_client.mock_calls == []
                assert mock_slack_client.mock_calls == []

    def test_creation_error_is_not_reported_as_validation_error(self):
        sut, mock_ack, mock_slack_client, mock_gs_client = self._build_sut()
        failure = InvalidBigchatName("AI 밋업 26-08-20 19:00~21:00")
        mock_gs_client.create_bigchat_sheet.side_effect = failure

        with self.assertRaises(InvalidBigchatName) as error:
            sut.run()

        assert error.exception is failure
        mock_ack.assert_called_once_with()
        mock_gs_client.get_url.assert_not_called()
        assert mock_slack_client.mock_calls == []

    def test_fallback_to_response_url_when_bot_not_in_channel(self):
        """봇이 채널에 없으면 대체 안내를 보내고 사전 등록은 건너뛴다."""
        for error in ("not_in_channel", "channel_not_found"):
            with self.subTest(error=error):
                sut, mock_ack, mock_slack_client, _ = self._build_sut()
                mock_slack_client.send_thread_message.side_effect = SlackApiError(
                    "boom", {"error": error}
                )

                result = sut.run()

                assert result is True
                mock_slack_client.send_response_url_message.assert_called_once_with(
                    response_url=sut.response_url,
                    msg=(
                        f"시트(<{self.SHEET_URL}|AI 밋업 26-08-20 19:00~21:00>)는 만들었는데, "
                        "내가 이 채널에 없어서 스레드에 답글을 못 달았어.\n"
                        "나를 채널에 초대한 뒤 위 시트 링크를 스레드에 공유해줘. "
                        "그래야 이모지로 참여 신청을 받을 수 있어!"
                    ),
                )
                mock_slack_client.get_emoji.assert_not_called()

    def test_unexpected_slack_error_is_raised(self):
        sut, _, mock_slack_client, _ = self._build_sut()
        mock_slack_client.send_thread_message.side_effect = SlackApiError(
            "boom", {"error": "ratelimited"}
        )

        with self.assertRaises(SlackApiError):
            sut.run()

        mock_slack_client.send_response_url_message.assert_not_called()
