import unittest
from unittest.mock import MagicMock, patch

from test.handler.bigchat.sample_data import create_sample_reaction_added_event

from config.env_config import envs
from handler.bigchat.join_bigchat import JoinBigchat
from handler.loading_emoji import LoadingEmoji
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
        mock_gs_client.append_row_if_absent.assert_called_once()
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

        mock_gs_client.append_row_if_absent.assert_called_once()
        assert result is True
        assert (
            mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "blocks"
            ]
            is None
        )

    def test_run_when_already_registered_skips_duplicate(self):
        """시트 생성 직후의 일괄 등록(#89)과 동시에 처리됐거나 이벤트가 중복
        전달된 경우, 중복 행을 만들지 않고 이미 등록됐다고만 알려준다."""
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
        mock_gs_client.append_row_if_absent.return_value = False
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

        assert result is True
        assert "이미 등록되어 있어" in mock_slack_client.send_message.call_args.kwargs["msg"]
        mock_slack_client.send_message_only_visible_to_user.assert_not_called()

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
        mock_gs_client.append_row_if_absent.side_effect = WorksheetNotFound("161837744")
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


class TestJoinBigchatLoadingEmoji(unittest.TestCase):
    """loading 이모지는 실제 등록 작업 전후에만 붙었다 떨어져야 한다."""

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
        return JoinBigchat(
            event,
            "gogo",
            mock_slack_client,
            mock_gs_client,
            mock_member_manager,
            loading_emoji=LoadingEmoji(
                mock_slack_client, event["item"]["channel"], event["item"]["ts"]
            ),
        )

    def test_not_attached_when_reaction_is_not_the_target_emoji(self):
        event = create_sample_reaction_added_event("thinking")
        mock_slack_client = MagicMock()

        assert (
            self._sut(event, mock_slack_client, MagicMock(), MagicMock()).run() is False
        )

        mock_slack_client.add_emoji.assert_not_called()
        mock_slack_client.remove_emoji.assert_not_called()

    def test_not_attached_when_message_has_no_bigchat_sheet(self):
        """빅챗 글이 아닌 아무 메시지에 이모지를 달아도 아무 동작이 없으므로 이모지를 붙이지 않는다."""
        event = create_sample_reaction_added_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            self._message(event["item"]["ts"], "점심 뭐 먹지")
        ]

        assert (
            self._sut(event, mock_slack_client, MagicMock(), MagicMock()).run() is False
        )

        mock_slack_client.add_emoji.assert_not_called()
        mock_slack_client.remove_emoji.assert_not_called()

    def test_not_attached_when_reaction_is_on_a_reply(self):
        event = create_sample_reaction_added_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            self._message("1688801100.000000", "스레드 첫 글"),
        ]

        assert (
            self._sut(event, mock_slack_client, MagicMock(), MagicMock()).run() is False
        )

        mock_slack_client.add_emoji.assert_not_called()

    def test_wraps_the_actual_registration(self):
        event = create_sample_reaction_added_event("gogo")
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
        # 시트 조회(no-op 판별)는 이모지 없이, 실제 등록은 이모지를 붙인 채로 진행한다
        call_names = [c[0] for c in mock_slack_client.mock_calls]
        assert call_names.index("get_replies") < call_names.index("add_emoji")
        assert call_names.index("add_emoji") < call_names.index("send_message")
        assert call_names.index("send_message") < call_names.index("remove_emoji")

    def test_removed_even_when_registration_fails(self):
        event = create_sample_reaction_added_event("gogo")
        mock_slack_client = MagicMock()
        mock_slack_client.get_replies.return_value = [
            self._message(
                event["item"]["ts"],
                "새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=161837744|구글스프레드 시트>",
            )
        ]
        mock_member_manager = MagicMock()
        mock_member_manager.find.side_effect = RuntimeError("스프레드시트 접속 실패")

        with self.assertRaises(RuntimeError):
            self._sut(event, mock_slack_client, MagicMock(), mock_member_manager).run()

        mock_slack_client.add_emoji.assert_called_once()
        mock_slack_client.remove_emoji.assert_called_once()
