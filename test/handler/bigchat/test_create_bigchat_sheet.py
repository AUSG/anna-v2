import unittest
from unittest.mock import MagicMock

from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from implementation.slack_client import Reaction
from implementation.member_finder import Member, MemberManager
from test.handler.bigchat.sample_data import create_sample_app_mention_event


class TestCreateBigchatSheet(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.run()

        mock_gs_client.create_bigchat_sheet.assert_called_once()
        mock_gs_client.get_url.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert "새로운 빅챗, 등록 완료!" in mock_slack_client.send_message.call_args.kwargs["msg"]

    def test_not_run_by_command_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.run()

        mock_gs_client.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_not_run_by_sheet_name_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 \n\n\n\n")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.run()

        mock_gs_client.assert_not_called()
        mock_slack_client.send_message.assert_called_once()
        assert result is False
        assert "시트 이름이 입력되지 않았어. 다시 입력해줘!" in mock_slack_client.send_message.call_args.kwargs["msg"]

    def test_gogo_pressed_while_building_spreadsheet(self):
        """빅챗 시트 생성이 완료되기 이전에 등록을 시도한(GOGO 이모지를 누른)
        인원들이 누락되지 않고 빅챗에 등록되었는지 확인합니다.
        """
        event = create_sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 빅챗 24-08-01")
        mock_slack_client = MagicMock()
        mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo",
            users=["U01BN035Y6L"],
            count=1,
        )
        mock_gs_client = MagicMock()
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="김동주",
            eng_name="Kim Dongjoo",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        MemberManager.get_instance = MagicMock(return_value=mock_member_manager)

        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        assert sut.run()

        mock_member_manager.find.assert_called_once()
        mock_slack_client.get_emoji.assert_called_once()
        mock_gs_client.append_row.assert_called_once()
