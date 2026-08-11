import unittest
from unittest.mock import MagicMock, patch

from test.handler.bigchat.sample_data import create_sample_reaction_added_event

from config.env_config import envs
from handler.bigchat.join_bigchat import JoinBigchat
from implementation.google_spreadsheet_client import WorksheetNotFound
from implementation.member_finder import Member
from implementation.slack_client import Message


class TestJoinBigchat(unittest.TestCase):
    def test_run(self):
        event = create_sample_reaction_added_event("gogo")
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
        mock_gs_client = MagicMock()
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="문성혁",
            eng_name="Moon Seonghyeok",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        sut = JoinBigchat(
            event, "gogo", mock_slack_client, mock_gs_client, mock_member_manager
        )

        result = sut.run()

        mock_member_manager.find.assert_called_once()
        mock_slack_client.get_replies.assert_called_once()
        mock_gs_client.append_row.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        mock_slack_client.send_message_only_visible_to_user.assert_called_once()
        assert "등록 완료!" in mock_slack_client.send_message.call_args.kwargs["msg"]
        assert (
            "네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!"
            in mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "msg"
            ]
        )
        assert result is True

    def test_run_with_old_format_sheet_registers_without_buttons(self):
        """구형식 시트여도 참가 신청은 그대로 성공하고, 캘린더 버튼만 생략된다."""
        event = create_sample_reaction_added_event("gogo")
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
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "빅챗 23-07-31"  # 구형식
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="문성혁",
            eng_name="Moon Seonghyeok",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        sut = JoinBigchat(
            event, "gogo", mock_slack_client, mock_gs_client, mock_member_manager
        )

        result = sut.run()

        mock_gs_client.append_row.assert_called_once()
        assert result is True
        assert (
            mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "blocks"
            ]
            is None
        )

    def test_run_with_deleted_sheet_notifies_user(self):
        """시트가 이미 삭제된 경우, 전용 안내 메시지를 보내고 False 를 반환한다."""
        event = create_sample_reaction_added_event("gogo")
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
        mock_gs_client = MagicMock()
        mock_gs_client.append_row.side_effect = WorksheetNotFound("161837744")
        mock_member_manager = MagicMock()
        mock_member_manager.find.return_value = Member(
            kor_name="문성혁",
            eng_name="Moon Seonghyeok",
            email="email",
            phone="phone",
            school_name_or_company_name="school_name_or_company_name",
        )
        sut = JoinBigchat(
            event, "gogo", mock_slack_client, mock_gs_client, mock_member_manager
        )

        result = sut.run()

        assert result is False
        mock_slack_client.send_message.assert_called_once()
        assert (
            "이 빅챗의 신청 시트를 찾을 수 없어"
            in mock_slack_client.send_message.call_args.kwargs["msg"]
        )
        mock_slack_client.send_message_only_visible_to_user.assert_not_called()

    def test_build_calendar_blocks_with_new_format_sheet(self):
        event = create_sample_reaction_added_event("gogo")
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
        sut = JoinBigchat(event, "gogo", MagicMock(), mock_gs_client, MagicMock())

        with patch.object(envs, "ICS_TOKEN_SECRET", "testsecret"):
            blocks = sut._build_calendar_blocks("등록했어", 161837744)

        assert blocks is not None
        buttons = blocks[1]["elements"]
        # 두 버튼 모두 같은 서명 쿼리를 달고 서버를 가리킨다 (gcal은 302 리다이렉트, ics는 다운로드)
        assert [b["action_id"] for b in buttons] == ["calendar_gcal", "calendar_ics"]
        gcal_url, ics_url = buttons[0]["url"], buttons[1]["url"]
        assert "/bigchat/161837744/gcal?" in gcal_url
        assert "/bigchat/161837744/event.ics?" in ics_url
        assert gcal_url.split("?")[1] == ics_url.split("?")[1]
        assert "token=" in gcal_url and "channel=" in gcal_url and "ts=" in gcal_url

    def test_build_calendar_blocks_without_secret(self):
        event = create_sample_reaction_added_event("gogo")
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
        sut = JoinBigchat(event, "gogo", MagicMock(), mock_gs_client, MagicMock())

        blocks = sut._build_calendar_blocks("등록했어", 161837744)

        assert blocks is None  # 시크릿 미설정이면 버튼 없이 기존 메시지만

    def test_build_calendar_blocks_with_old_format_sheet(self):
        event = create_sample_reaction_added_event("gogo")
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "빅챗 23-07-31"
        sut = JoinBigchat(event, "gogo", MagicMock(), mock_gs_client, MagicMock())

        with patch.object(envs, "ICS_TOKEN_SECRET", "testsecret"):
            blocks = sut._build_calendar_blocks("등록했어", 161837744)

        assert blocks is None
