import unittest
from unittest.mock import MagicMock

from slack_sdk.errors import SlackApiError

from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from implementation.member_finder import Member, MemberLackInfo, MemberNotFound
from implementation.slack_client import Reaction, SlackClient
from test.handler.bigchat.sample_data import create_sample_app_mention_event

SAMPLE_MEMBER = Member(
    kor_name="김동주",
    eng_name="Kim Dongjoo",
    email="email",
    phone="phone",
    school_name_or_company_name="school_name_or_company_name",
)


def create_sut(event, mock_slack_client, mock_gs_client, mock_member_manager=None):
    return CreateBigchatSheet(
        event,
        mock_slack_client,
        mock_gs_client,
        mock_member_manager or MagicMock(),
        "gogo",
    )


class TestCreateBigchatSheet(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event(
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        )
        mock_slack_client = MagicMock()
        mock_slack_client.get_emoji.return_value = None  # 미리 눌린 이모지 없음
        mock_gs_client = MagicMock()
        sut = create_sut(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.create_bigchat_sheet.assert_called_once_with(
            "AI 밋업 26-08-20 19:00~21:00"
        )
        mock_gs_client.get_url.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert (
            "새로운 빅챗, 등록 완료!"
            in mock_slack_client.send_message.call_args.kwargs["msg"]
        )

    def test_not_run_by_command_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = create_sut(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_rejected_by_invalid_format(self):
        for text in [
            "<@U01BN035Y6L> 새로운 빅챗 \n\n\n\n",  # 이름 없음
            "<@U01BN035Y6L> 새로운 빅챗 빅챗 23-07-31",  # 시간 없음 (구형식)
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-02-30 19:00~21:00",  # 존재하지 않는 날짜
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 21:00~19:00",  # 종료가 시작보다 빠름
        ]:
            event = create_sample_app_mention_event(text)
            mock_slack_client = MagicMock()
            mock_gs_client = MagicMock()
            sut = create_sut(event, mock_slack_client, mock_gs_client)

            result = sut.handle_mention()

            mock_gs_client.create_bigchat_sheet.assert_not_called()
            mock_slack_client.send_message.assert_not_called()
            mock_slack_client.send_message_only_visible_to_user.assert_called_once()
            assert result is False
            assert (
                "형식이 올바르지 않아서 빅챗을 만들지 않았어"
                in mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                    "msg"
                ]
            )


class TestCreateBigchatSheetEarlyReactionBackfill(unittest.TestCase):
    """시트 생성 전에 모집글에 :gogo:를 누른 사람들의 일괄 등록 (#89)"""

    WORKSHEET_ID = 161837744

    def setUp(self):
        self.event = create_sample_app_mention_event(
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        )
        self.mock_slack_client = MagicMock()
        self.mock_gs_client = MagicMock()
        self.mock_gs_client.create_bigchat_sheet.return_value = self.WORKSHEET_ID
        self.mock_gs_client.append_row_if_absent.return_value = True
        self.mock_member_manager = MagicMock()
        self.mock_member_manager.find.return_value = SAMPLE_MEMBER
        self.sut = create_sut(
            self.event,
            self.mock_slack_client,
            self.mock_gs_client,
            self.mock_member_manager,
        )

    def test_registers_users_who_reacted_before_sheet_created(self):
        self.mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo", users=["U01BN035Y6L"], count=1
        )

        assert self.sut.handle_mention()

        # reaction 은 멘션이 달린 글(모집글, 스레드 부모)에서 읽어야 한다
        self.mock_slack_client.get_emoji.assert_called_once_with(
            channel=self.event["channel"],
            ts=self.event["thread_ts"],
            emoji_name="gogo",
        )
        self.mock_member_manager.find.assert_called_once_with("U01BN035Y6L")
        self.mock_gs_client.append_row_if_absent.assert_called_once_with(
            self.WORKSHEET_ID, SAMPLE_MEMBER.transform_for_spreadsheet()
        )
        # 시트 링크 안내는 send_message, 일괄 등록 안내는 (say 컨텍스트가 없는
        # 모달 경로와 공유하는) send_thread_message 로 나간다
        self.mock_slack_client.send_message.assert_called_once()
        self.mock_slack_client.send_thread_message.assert_called_once()
        group_kwargs = self.mock_slack_client.send_thread_message.call_args.kwargs
        assert "지금 등록 완료했어" in group_kwargs["msg"]
        assert group_kwargs["ts"] == self.event["thread_ts"]
        # 등록 정보는 본인에게만 보이는 메시지로 안내
        self.mock_slack_client.send_message_only_visible_to_user.assert_called_once()
        ephemeral_kwargs = (
            self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs
        )
        assert ephemeral_kwargs["user_id"] == "U01BN035Y6L"
        assert "네 신청 정보를 아래와 같이 등록했어" in ephemeral_kwargs["msg"]

    def test_posts_sheet_link_before_reading_reactions(self):
        """링크를 올린 '뒤에' reaction 을 읽어야 그 사이에 눌린 reaction 이
        JoinBigchat 과 일괄 등록 중 어느 한쪽에는 반드시 잡힌다."""
        self.mock_slack_client.get_emoji.return_value = None

        assert self.sut.handle_mention()

        call_names = [name for name, _, _ in self.mock_slack_client.mock_calls]
        assert call_names.index("send_message") < call_names.index("get_emoji")

    def test_skips_users_already_registered(self):
        self.mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo", users=["U01BN035Y6L"], count=1
        )
        self.mock_gs_client.append_row_if_absent.return_value = False

        assert self.sut.handle_mention()

        self.mock_slack_client.send_message.assert_called_once()  # 시트 링크 안내만
        self.mock_slack_client.send_thread_message.assert_not_called()
        self.mock_slack_client.send_message_only_visible_to_user.assert_not_called()

    def test_notifies_users_whose_member_info_is_missing(self):
        self.mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo", users=["U01BN035Y6L"], count=1
        )
        self.mock_member_manager.find.side_effect = MemberNotFound()

        assert self.sut.handle_mention()

        self.mock_gs_client.append_row_if_absent.assert_not_called()
        assert (
            "네 정보를 찾지 못했어"
            in self.mock_slack_client.send_thread_message.call_args.kwargs["msg"]
        )

    def test_registers_multiple_users_and_reports_each_outcome(self):
        self.mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo", users=["U_OK", "U_LACK", "U_DUP"], count=3
        )
        self.mock_member_manager.find.side_effect = [
            SAMPLE_MEMBER,
            MemberLackInfo(),
            SAMPLE_MEMBER,
        ]
        self.mock_gs_client.append_row_if_absent.side_effect = [True, False]

        assert self.sut.handle_mention()

        assert self.mock_gs_client.append_row_if_absent.call_count == 2
        self.mock_slack_client.send_message.assert_called_once()  # 링크 안내
        messages = [
            c.kwargs["msg"]
            for c in self.mock_slack_client.send_thread_message.call_args_list
        ]
        assert len(messages) == 2  # 정보 누락 안내 + 일괄 등록 안내
        assert "네 정보에 누락된 값이 있어" in messages[0]
        assert "<@U_LACK>" in messages[0]
        assert "<@U_OK>" in messages[1]
        assert "<@U_DUP>" not in messages[1]  # 이미 등록된 사람은 재안내하지 않는다
        self.mock_slack_client.send_message_only_visible_to_user.assert_called_once()
        assert (
            self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "user_id"
            ]
            == "U_OK"
        )

    def test_continues_ephemeral_fanout_when_one_user_unreachable(self):
        """채널을 떠난 반응자에게 ephemeral 발송이 실패해도 나머지 인원 안내와
        전체 처리는 계속되어야 한다."""
        self.mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo", users=["U_LEFT", "U_OK"], count=2
        )
        self.mock_slack_client.send_message_only_visible_to_user.side_effect = [
            SlackApiError("user_not_in_channel", MagicMock()),
            None,
        ]

        assert self.sut.handle_mention()

        assert (
            self.mock_slack_client.send_message_only_visible_to_user.call_count == 2
        )
        # 링크 안내 1 + 일괄 등록 안내 1, 경고 메시지 없음
        self.mock_slack_client.send_message.assert_called_once()
        self.mock_slack_client.send_thread_message.assert_called_once()

    def test_backfill_failure_warns_thread_instead_of_crashing(self):
        """시트 생성이 이미 성공했으므로, 일괄 등록 실패는 전역 에러('다시
        시도해줘')로 번지지 않고 스레드 경고로 끝나야 한다."""
        self.mock_slack_client.get_emoji.return_value = Reaction(
            name="gogo", users=["U01BN035Y6L"], count=1
        )
        self.mock_gs_client.append_row_if_absent.side_effect = Exception("quota")

        assert self.sut.handle_mention()

        assert (
            "문제가 생겨서 멈췄어"
            in self.mock_slack_client.send_thread_message.call_args.kwargs["msg"]
        )

    def test_reads_reactions_from_mention_itself_when_not_in_thread(self):
        del self.event["thread_ts"]
        del self.event["parent_user_id"]
        self.mock_slack_client.get_emoji.return_value = None
        sut = create_sut(
            self.event,
            self.mock_slack_client,
            self.mock_gs_client,
            self.mock_member_manager,
        )

        assert sut.handle_mention()

        self.mock_slack_client.get_emoji.assert_called_once_with(
            channel=self.event["channel"],
            ts=self.event["ts"],
            emoji_name="gogo",
        )
        self.mock_gs_client.append_row_if_absent.assert_not_called()

    def test_backfill_against_real_slack_client_contract(self):
        """원본 PR #90의 치명 버그(get_emoji 호출부 kwarg 불일치)가 재발하지
        않도록, mock 이 아닌 실제 SlackClient 를 끼워 계약을 고정한다."""
        mock_web_client = MagicMock()
        mock_web_client.reactions_get.return_value = {
            "message": {
                "reactions": [{"name": "gogo", "users": ["U01BN035Y6L"], "count": 1}]
            }
        }
        slack_client = SlackClient(MagicMock(), mock_web_client)
        sut = CreateBigchatSheet(
            self.event,
            slack_client,
            self.mock_gs_client,
            self.mock_member_manager,
            "gogo",
        )

        assert sut.handle_mention()

        mock_web_client.reactions_get.assert_called_once_with(
            channel=self.event["channel"],
            timestamp=self.event["thread_ts"],
            full=True,
        )
        self.mock_gs_client.append_row_if_absent.assert_called_once()
        mock_web_client.chat_postMessage.assert_called_once()  # 일괄 등록 안내
        mock_web_client.chat_postEphemeral.assert_called_once()
