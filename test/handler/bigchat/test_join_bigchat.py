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
        mock_slack_client = MagicMock()
        mock_slack_client.get_permalink.return_value = (
            "https://ausg.slack.com/archives/C03SZTDEDK3/p1688801145307229"
        )
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
        sut = JoinBigchat(event, "gogo", mock_slack_client, mock_gs_client, MagicMock())

        with patch.object(envs, "ICS_TOKEN_SECRET", "testsecret"):
            blocks = sut._build_calendar_blocks("등록했어", 161837744, "이번 빅챗 소개글입니다")

        assert blocks is not None
        buttons = blocks[1]["elements"]
        assert [b["action_id"] for b in buttons] == ["calendar_gcal", "calendar_ics"]
        gcal_url, ics_url = buttons[0]["url"], buttons[1]["url"]
        # gcal은 직링크여야 한다 — 서버 302 경유 시 모바일 앱 링크 핸드오프가 끊긴다
        assert gcal_url.startswith("https://calendar.google.com/calendar/render?")
        # gcal 본문은 permalink가 맨 앞, 그 아래 소개글 — 잘려도 permalink는 항상 남는다
        assert "ausg.slack.com" in gcal_url
        assert "%EC%86%8C%EA%B0%9C%EA%B8%80" in gcal_url  # "소개글" (intro도 이어붙음)
        assert "/bigchat/161837744/event.ics?" in ics_url
        assert "token=" in ics_url and "channel=" in ics_url and "ts=" in ics_url

    def test_build_calendar_blocks_keeps_permalink_when_long_intro_truncated(self):
        event = create_sample_reaction_added_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_permalink.return_value = (
            "https://ausg.slack.com/archives/C03SZTDEDK3/p1688801145307229"
        )
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
        sut = JoinBigchat(event, "gogo", mock_slack_client, mock_gs_client, MagicMock())

        blocks = sut._build_calendar_blocks("등록했어", 161837744, "긴 소개글 " * 2000)

        gcal_url = blocks[1]["elements"][0]["url"]
        assert "ausg.slack.com" in gcal_url  # 소개글이 잘려도 맨 앞의 permalink는 남는다

    def test_build_calendar_blocks_falls_back_to_intro_without_permalink(self):
        event = create_sample_reaction_added_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_permalink.return_value = None
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
        sut = JoinBigchat(event, "gogo", mock_slack_client, mock_gs_client, MagicMock())

        blocks = sut._build_calendar_blocks("등록했어", 161837744, "이번 빅챗 소개글입니다")

        gcal_url = blocks[1]["elements"][0]["url"]
        assert "details=" in gcal_url  # permalink 실패 시 (잘린) 소개글로 폴백

    def test_build_calendar_blocks_without_secret_has_gcal_only(self):
        event = create_sample_reaction_added_event("gogo")
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "AI 밋업 26-08-20 19:00~21:00"
        sut = JoinBigchat(event, "gogo", MagicMock(), mock_gs_client, MagicMock())

        blocks = sut._build_calendar_blocks("등록했어", 161837744, "소개글")

        buttons = blocks[1]["elements"]
        assert [b["action_id"] for b in buttons] == ["calendar_gcal"]

    def test_build_calendar_blocks_with_old_format_sheet(self):
        event = create_sample_reaction_added_event("gogo")
        mock_gs_client = MagicMock()
        mock_gs_client.get_worksheet_title.return_value = "빅챗 23-07-31"
        sut = JoinBigchat(event, "gogo", MagicMock(), mock_gs_client, MagicMock())

        with patch.object(envs, "ICS_TOKEN_SECRET", "testsecret"):
            blocks = sut._build_calendar_blocks("등록했어", 161837744, "소개글")

        assert blocks is None
