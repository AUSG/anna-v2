import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_reaction_removed_event

from handler.bigchat.abandon_bigchat import AbandonBigchat
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
