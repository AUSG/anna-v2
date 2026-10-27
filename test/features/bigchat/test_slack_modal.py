import json
import unittest
from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from features.bigchat.presentation.messages import (
    bigchat_created_message,
    bot_not_in_channel_message,
)
from features.bigchat.presentation.modals import (
    CREATE_BIGCHAT_VIEW_ID,
    DATE_BLOCK,
    END_BLOCK,
    NAME_BLOCK,
    START_BLOCK,
    create_bigchat_view,
)
from features.bigchat.services.sheet_link import SPREADSHEET_PAT
from features.bigchat.slack import (
    open_create_bigchat_modal,
    submit_create_bigchat_modal,
)
from shared.slack_events import ShortcutPayload, ViewSubmission
from test.fixtures.runtime import fake_runtime, fake_slack
from test.fixtures.slack_events import (
    create_sample_message_shortcut_body,
    create_sample_view_submission_body,
)

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"


class TestPayloadParsing(unittest.TestCase):
    def test_shortcut_on_plain_message(self):
        body = create_sample_message_shortcut_body()

        payload = ShortcutPayload.from_payload(body)

        assert payload.channel == "C03SZTDEDK3"
        assert payload.thread_ts == "1688801145.307229"
        assert payload.user == "UQJ8HQJG5"
        assert payload.trigger_id == body["trigger_id"]
        assert payload.response_url == body["response_url"]

    def test_shortcut_on_thread_reply_anchors_to_thread_root(self):
        body = create_sample_message_shortcut_body(thread_ts="1688800000.000001")

        assert ShortcutPayload.from_payload(body).thread_ts == "1688800000.000001"

    def test_view_submission(self):
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )

        submission = ViewSubmission.from_payload(body)

        assert submission.channel == "C03SZTDEDK3"
        assert submission.thread_ts == "1688801145.307229"
        assert submission.user == "UQJ8HQJG5"
        assert (
            submission.response_url
            == "https://hooks.slack.com/app/TQLEG4B38/1234567890/abcdefg"
        )
        assert submission.values[NAME_BLOCK]["value"]["value"] == "AI 밋업"


class TestOpenCreateBigchatModal(unittest.TestCase):
    def test_run(self):
        body = create_sample_message_shortcut_body(thread_ts="1688800000.000001")
        payload = ShortcutPayload.from_payload(body)
        slack = fake_slack()

        result = open_create_bigchat_modal(payload, slack)

        assert result is True
        slack.open_view.assert_called_once_with(
            payload.trigger_id,
            create_bigchat_view(
                "C03SZTDEDK3", "1688800000.000001", payload.response_url
            ),
        )

        view = slack.open_view.call_args.args[1]
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
        assert metadata["thread_ts"] == "1688800000.000001"
        assert metadata["response_url"] == body["response_url"]


class TestSubmitCreateBigchatModal(unittest.TestCase):
    SHEET_URL = "https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid=987654321"

    def _build(self, name="AI 밋업", date="2026-08-20", start="19:00", end="21:00"):
        body = create_sample_view_submission_body(name, date, start, end)
        self.submission = ViewSubmission.from_payload(body)
        self.ack = MagicMock(name="ack")
        self.runtime = fake_runtime()
        self.slack = self.runtime.slack
        self.slack.get_reaction.return_value = None  # 미리 눌린 이모지 없음
        self.sheets = self.runtime.sheets()
        self.sheets.create_bigchat_sheet.return_value = 987654321
        self.sheets.get_url.return_value = self.SHEET_URL
        self.members = self.runtime.members()

    def _run(self):
        return submit_create_bigchat_modal(
            self.submission, self.ack, self.slack, self.runtime
        )

    def test_run(self):
        self._build()

        result = self._run()

        assert result is True
        self.ack.assert_called_once_with()
        self.sheets.create_bigchat_sheet.assert_called_once_with(SHEET_NAME)
        self.slack.send_thread_message.assert_called_once_with(
            "C03SZTDEDK3",
            "1688801145.307229",
            bigchat_created_message(self.SHEET_URL, SHEET_NAME),
        )
        # :gogo: 참여 흐름(join_bigchat)이 이 답글에서 시트 gid를 찾아낼 수 있어야 한다
        msg = self.slack.send_thread_message.call_args.args[2]
        assert SPREADSHEET_PAT.search(msg).groups()[0] == "987654321"
        # 링크를 올린 뒤, 모달을 띄운 메시지가 속한 스레드의 첫 글(모집글)에서 reaction 을 읽는다
        call_names = [name for name, _, _ in self.slack.mock_calls]
        assert call_names.index("send_thread_message") < call_names.index(
            "get_reaction"
        )
        self.slack.get_reaction.assert_called_once_with(
            "C03SZTDEDK3", "1688801145.307229", "gogo"
        )
        assert self.members.mock_calls == []

    def test_ack_is_called_before_the_sheet_is_created(self):
        """3초 안에 응답해야 하므로 시트 생성 전에 모달을 닫는다."""
        self._build()
        trace = MagicMock()
        trace.attach_mock(self.ack, "ack")
        trace.attach_mock(self.sheets, "sheets")

        self._run()

        call_names = [name for name, _, _ in trace.mock_calls]
        assert call_names.index("ack") < call_names.index("sheets.create_bigchat_sheet")

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
                self._build(**overrides)

                assert self._run() is False

                self.ack.assert_called_once_with(
                    response_action="errors", errors=expected
                )
                assert self.sheets.mock_calls == []
                assert self.slack.mock_calls == []

    def test_ack_failure_does_not_create_a_sheet(self):
        for date in ("2026-08-20", "2026-02-30"):
            with self.subTest(date=date):
                self._build(date=date)
                failure = RuntimeError("ACK 실패")
                self.ack.side_effect = failure

                with self.assertRaises(RuntimeError) as error:
                    self._run()

                assert error.exception is failure
                assert failure.__context__ is None
                self.ack.assert_called_once()
                assert self.sheets.mock_calls == []
                assert self.slack.mock_calls == []

    def test_creation_error_is_not_reported_as_validation_error(self):
        self._build()
        failure = RuntimeError("시트 생성 실패")
        self.sheets.create_bigchat_sheet.side_effect = failure

        with self.assertRaises(RuntimeError) as error:
            self._run()

        assert error.exception is failure
        self.ack.assert_called_once_with()
        self.sheets.get_url.assert_not_called()
        assert self.slack.mock_calls == []

    def test_fallback_to_response_url_when_bot_not_in_channel(self):
        """봇이 채널에 없으면 대체 안내를 보내고 사전 등록은 건너뛴다."""
        for error in ("not_in_channel", "channel_not_found"):
            with self.subTest(error=error):
                self._build()
                self.slack.send_thread_message.side_effect = SlackApiError(
                    "boom", {"error": error}
                )

                result = self._run()

                assert result is True
                self.slack.send_response_url_message.assert_called_once_with(
                    self.submission.response_url,
                    bot_not_in_channel_message(self.SHEET_URL, SHEET_NAME),
                )
                assert self.slack.send_response_url_message.call_args.args[1] == (
                    f"시트(<{self.SHEET_URL}|{SHEET_NAME}>)는 만들었는데, "
                    "내가 이 채널에 없어서 스레드에 답글을 못 달았어.\n"
                    "나를 채널에 초대한 뒤 위 시트 링크를 스레드에 공유해줘. "
                    "그래야 이모지로 참여 신청을 받을 수 있어!"
                )
                self.slack.get_reaction.assert_not_called()

    def test_unexpected_slack_error_is_raised(self):
        self._build()
        self.slack.send_thread_message.side_effect = SlackApiError(
            "boom", {"error": "ratelimited"}
        )

        with self.assertRaises(SlackApiError):
            self._run()

        self.slack.send_response_url_message.assert_not_called()
        self.slack.get_reaction.assert_not_called()
