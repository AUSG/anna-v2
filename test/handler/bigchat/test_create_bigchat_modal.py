import json
import unittest
from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from handler.bigchat.create_bigchat_modal import (
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
from handler.bigchat.join_bigchat import SPREADSHEET_PAT
from test.handler.bigchat.sample_data import (
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
        mock_gs_client = MagicMock()
        mock_gs_client.create_bigchat_sheet.return_value = 987654321
        mock_gs_client.get_url.return_value = self.SHEET_URL
        sut = SubmitCreateBigchatModal(
            event, mock_ack, mock_slack_client, mock_gs_client
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
        mock_slack_client.send_thread_message.assert_called_once()
        kwargs = mock_slack_client.send_thread_message.call_args.kwargs
        assert kwargs["channel"] == "C03SZTDEDK3"
        assert kwargs["ts"] == "1688801145.307229"
        assert "새로운 빅챗, 등록 완료!" in kwargs["msg"]

    def test_created_message_is_discoverable_by_join_bigchat(self):
        # :gogo: 참여 흐름(JoinBigchat)이 이 답글에서 시트 gid를 찾아낼 수 있어야 한다
        sut, _, mock_slack_client, _ = self._build_sut()

        sut.run()

        msg = mock_slack_client.send_thread_message.call_args.kwargs["msg"]
        assert SPREADSHEET_PAT.search(msg).groups()[0] == "987654321"

    def test_rejected_by_end_not_after_start(self):
        for start, end in [("21:00", "19:00"), ("19:00", "19:00")]:
            sut, mock_ack, mock_slack_client, mock_gs_client = self._build_sut(
                start=start, end=end
            )

            result = sut.run()

            assert result is False
            mock_ack.assert_called_once()
            kwargs = mock_ack.call_args.kwargs
            assert kwargs["response_action"] == "errors"
            assert END_BLOCK in kwargs["errors"]
            mock_gs_client.create_bigchat_sheet.assert_not_called()
            mock_slack_client.send_thread_message.assert_not_called()

    def test_rejected_by_blank_name(self):
        sut, mock_ack, mock_slack_client, mock_gs_client = self._build_sut(name="   ")

        result = sut.run()

        assert result is False
        kwargs = mock_ack.call_args.kwargs
        assert kwargs["response_action"] == "errors"
        assert NAME_BLOCK in kwargs["errors"]
        mock_gs_client.create_bigchat_sheet.assert_not_called()

    def test_fallback_to_response_url_when_bot_not_in_channel(self):
        sut, mock_ack, mock_slack_client, _ = self._build_sut()
        mock_slack_client.send_thread_message.side_effect = SlackApiError(
            "boom", {"error": "not_in_channel"}
        )

        result = sut.run()

        assert result is True
        mock_slack_client.send_response_url_message.assert_called_once()
        kwargs = mock_slack_client.send_response_url_message.call_args.kwargs
        assert kwargs["response_url"] == sut.response_url
        assert self.SHEET_URL in kwargs["msg"]

    def test_unexpected_slack_error_is_raised(self):
        sut, _, mock_slack_client, _ = self._build_sut()
        mock_slack_client.send_thread_message.side_effect = SlackApiError(
            "boom", {"error": "ratelimited"}
        )

        with self.assertRaises(SlackApiError):
            sut.run()

        mock_slack_client.send_response_url_message.assert_not_called()
