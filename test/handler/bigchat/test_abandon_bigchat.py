import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_reaction_removed_event

from handler.bigchat.abandon_bigchat import AbandonBigchat
from handler.loading_emoji import LoadingEmoji
from implementation.google_spreadsheet_client import WorksheetNotFound
from implementation.member_finder import Member
from implementation.slack_client import Message


class TestAbandonBigchat(unittest.TestCase):
    def test_run(self):
        event = create_sample_reaction_removed_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            Message(
                ts=event["item"]["ts"],
                thread_ts="1689429129.825319",
                channel="C03SZTDEDK3",
                user="U01BN035Y6L",
                text="새로운 빅챗을 모집합니다!",
            ),
            Message(
                ts=event["item"]["ts"],
                thread_ts="1689429129.825319",
                channel="C03SZTDEDK3",
                user="U01BN035Y6L",
                text="새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=161837744|구글스프레드 시트>",
            ),
        ]
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="문성혁",
            eng_name="Moon Seonghyeok",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        mock_gs_client = MagicMock()
        sut = AbandonBigchat(
            event,
            "U01BN035Y6L",
            "gogo",
            mock_slack_client,
            mock_member_manager,
            mock_gs_client,
        )

        result = sut.run()

        mock_slack_client.get_replies.assert_called_once()
        mock_member_manager.find.assert_called_once()
        mock_gs_client.delete_row.assert_called_once()
        mock_slack_client.send_message_only_visible_to_user.assert_called_once()
        assert result is True
        assert (
            "등록을 취소했어."
            in mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "msg"
            ]
        )

    def test_run_with_deleted_sheet_notifies_user(self):
        """시트가 이미 삭제된 경우, 전용 안내 메시지를 보내고 False 를 반환한다."""
        event = create_sample_reaction_removed_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            Message(
                ts=event["item"]["ts"],
                thread_ts="1689429129.825319",
                channel="C03SZTDEDK3",
                user="U01BN035Y6L",
                text="새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=161837744|구글스프레드 시트>",
            ),
        ]
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="문성혁",
            eng_name="Moon Seonghyeok",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        mock_gs_client = MagicMock()
        mock_gs_client.delete_row.side_effect = WorksheetNotFound("161837744")
        sut = AbandonBigchat(
            event,
            "U01BN035Y6L",
            "gogo",
            mock_slack_client,
            mock_member_manager,
            mock_gs_client,
        )

        result = sut.run()

        assert result is False
        mock_slack_client.send_message.assert_called_once()
        assert (
            "이 빅챗의 신청 시트를 찾을 수 없어서 등록을 취소하지 못했어"
            in mock_slack_client.send_message.call_args.kwargs["msg"]
        )
        mock_slack_client.send_message_only_visible_to_user.assert_not_called()


class TestAbandonBigchatLoadingEmoji(unittest.TestCase):
    """loading 이모지는 실제 취소 작업 전후에만 붙었다 떨어져야 한다."""

    @staticmethod
    def _message(ts, text):
        return Message(
            ts=ts,
            thread_ts="1689429129.825319",
            channel="C03SZTDEDK3",
            user="U01BN035Y6L",
            text=text,
        )

    def _sut(self, event, mock_slack_client, mock_gs_client, mock_member_manager):
        return AbandonBigchat(
            event,
            "U01BN035Y6L",
            "gogo",
            mock_slack_client,
            mock_member_manager,
            mock_gs_client,
            loading_emoji=LoadingEmoji(
                mock_slack_client, event["item"]["channel"], event["item"]["ts"]
            ),
        )

    def test_not_attached_when_message_has_no_bigchat_sheet(self):
        event = create_sample_reaction_removed_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            self._message(event["item"]["ts"], "점심 뭐 먹지")
        ]

        assert (
            self._sut(event, mock_slack_client, MagicMock(), MagicMock()).run() is False
        )

        mock_slack_client.add_emoji.assert_not_called()
        mock_slack_client.remove_emoji.assert_not_called()

    def test_wraps_the_actual_cancellation(self):
        event = create_sample_reaction_removed_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            self._message(
                event["item"]["ts"],
                "새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=161837744|구글스프레드 시트>",
            )
        ]
        mock_gs_client = MagicMock()
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="문성혁",
            eng_name="Moon Seonghyeok",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )

        result = self._sut(
            event, mock_slack_client, mock_gs_client, mock_member_manager
        ).run()

        assert result is True
        mock_slack_client.add_emoji.assert_called_once_with(
            event["item"]["channel"], event["item"]["ts"], "loading"
        )
        mock_slack_client.remove_emoji.assert_called_once_with(
            event["item"]["channel"], event["item"]["ts"], "loading"
        )
        call_names = [c[0] for c in mock_slack_client.mock_calls]
        assert call_names.index("get_replies") < call_names.index("add_emoji")
        assert call_names.index("add_emoji") < call_names.index(
            "send_message_only_visible_to_user"
        )
        assert call_names.index("send_message_only_visible_to_user") < call_names.index(
            "remove_emoji"
        )
