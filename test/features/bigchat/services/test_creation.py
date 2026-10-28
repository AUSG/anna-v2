"""시트 생성 전에 모집글에 :gogo:를 누른 사람들의 일괄 등록 (#89)

멘션과 모달 핸들러가 공유하는 register_early_reacted_users를 직접 검사한다.
핸들러 테스트는 이 함수가 링크 게시 뒤에 올바른 모집글 위치로 호출되는지만 본다.
"""

import unittest
from unittest.mock import MagicMock, call

from slack_sdk.errors import SlackApiError

from features.bigchat.services.creation import register_early_reacted_users
from features.members.services.directory import Member, MemberLackInfo, MemberNotFound
from integrations.slack import Reaction, SlackClient
from test.fixtures.slack_events import create_sample_member

CHANNEL = "C03SZTDEDK3"
THREAD_TS = "1688801145.307229"
WORKSHEET_ID = 161837744
SAMPLE_MEMBER = create_sample_member()
SAMPLE_ROW = ["김동주", "school_name_or_company_name", "email", "phone"]


def _registration_info_call(user, member):
    return call(
        msg=(
            f"<@{user}> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!\n"
            "```\n"
            f"이름(영문): {member.kor_name}({member.eng_name})\n"
            f"핸드폰: {member.phone}\n"
            f"이메일: {member.email}\n"
            f"학교/회사: {member.school_name_or_company_name}\n"
            "```\n"
            "(참고로 이 메시지는 너만 볼 수 있어!)"
        ),
        channel=CHANNEL,
        ts=THREAD_TS,
        user_id=user,
    )


class TestRegisterEarlyReactedUsers(unittest.TestCase):
    def setUp(self):
        self.slack = MagicMock()
        self.sheets = MagicMock()
        self.sheets.append_row_if_absent.return_value = True
        self.members = MagicMock()
        self.members.find.return_value = SAMPLE_MEMBER

    def run_backfill(self, slack=None):
        register_early_reacted_users(
            slack or self.slack,
            self.sheets,
            self.members,
            "gogo",
            WORKSHEET_ID,
            channel=CHANNEL,
            thread_ts=THREAD_TS,
        )

    def test_does_nothing_when_nobody_reacted(self):
        for reaction in (None, Reaction(name="gogo", users=[], count=0)):
            with self.subTest(reaction=reaction):
                self.setUp()
                self.slack.get_emoji.return_value = reaction

                self.run_backfill()

                assert self.slack.mock_calls == [
                    call.get_emoji(channel=CHANNEL, ts=THREAD_TS, emoji_name="gogo")
                ]
                assert self.members.mock_calls == []
                assert self.sheets.mock_calls == []

    def test_registers_each_user_and_reports_each_outcome(self):
        self.slack.get_emoji.return_value = Reaction(
            name="gogo", users=["U_OK", "U_LACK", "U_NONE", "U_DUP"], count=4
        )
        self.members.find.side_effect = [
            SAMPLE_MEMBER,
            MemberLackInfo(),
            MemberNotFound(),
            SAMPLE_MEMBER,
        ]
        self.sheets.append_row_if_absent.side_effect = [True, False]

        self.run_backfill()

        assert self.members.find.call_args_list == [
            call("U_OK"),
            call("U_LACK"),
            call("U_NONE"),
            call("U_DUP"),
        ]
        assert self.sheets.append_row_if_absent.call_args_list == [
            call(WORKSHEET_ID, SAMPLE_ROW),
            call(WORKSHEET_ID, SAMPLE_ROW),
        ]
        assert self.slack.send_thread_message.call_args_list == [
            call(
                msg="<@U_LACK>, 네 정보에 누락된 값이 있어. 운영진에게 연락해줘!",
                channel=CHANNEL,
                ts=THREAD_TS,
            ),
            call(
                msg="<@U_NONE>, 네 정보를 찾지 못했어. 운영진에게 연락해줘!",
                channel=CHANNEL,
                ts=THREAD_TS,
            ),
            call(
                msg="<@U_OK> 시트가 만들어지기 전에 :gogo:를 눌러줬구나! 지금 등록 완료했어!",
                channel=CHANNEL,
                ts=THREAD_TS,
            ),
        ]
        # 등록 정보는 본인에게만 보이는 메시지로 안내
        assert self.slack.send_message_only_visible_to_user.call_args_list == [
            _registration_info_call("U_OK", SAMPLE_MEMBER)
        ]

    def test_continues_ephemeral_fanout_when_one_user_unreachable(self):
        """채널을 떠난 반응자에게 ephemeral 발송이 실패해도 나머지 인원 안내와
        전체 처리는 계속되어야 한다."""
        other = Member(
            kor_name="김철수",
            eng_name="Kim Chulsoo",
            email="Chulsoo@Example.com",
            phone="010-1234-5678",
            school_name_or_company_name="AUSG대",
        )
        self.members.find.side_effect = [SAMPLE_MEMBER, other]
        self.slack.get_emoji.return_value = Reaction(
            name="gogo", users=["U_LEFT", "U_OK"], count=2
        )
        self.slack.send_message_only_visible_to_user.side_effect = [
            SlackApiError("user_not_in_channel", MagicMock()),
            None,
        ]

        expected_info = [
            _registration_info_call("U_LEFT", SAMPLE_MEMBER),
            _registration_info_call("U_OK", other),
        ]

        self.run_backfill()

        assert self.members.find.call_args_list == [call("U_LEFT"), call("U_OK")]
        assert self.sheets.append_row_if_absent.call_args_list == [
            call(WORKSHEET_ID, SAMPLE_ROW),
            call(
                WORKSHEET_ID,
                ["김철수", "AUSG대", "Chulsoo@Example.com", "010-1234-5678"],
            ),
        ]
        assert (
            self.slack.send_message_only_visible_to_user.call_args_list == expected_info
        )
        # 일괄 등록 안내 1, 경고 메시지 없음
        self.slack.send_thread_message.assert_called_once()

    def test_failure_warns_thread_instead_of_crashing(self):
        """시트 생성이 이미 성공했으므로, 일괄 등록 실패는 전역 에러('다시
        시도해줘')로 번지지 않고 스레드 경고로 끝나야 한다."""
        self.slack.get_emoji.return_value = Reaction(
            name="gogo", users=["U01BN035Y6L"], count=1
        )
        self.sheets.append_row_if_absent.side_effect = Exception("quota")

        self.run_backfill()

        self.slack.send_thread_message.assert_called_once_with(
            msg=(
                "미리 눌린 :gogo: 자동 등록을 처리하다 문제가 생겨서 멈췄어. "
                "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!"
            ),
            channel=CHANNEL,
            ts=THREAD_TS,
        )

    def test_against_real_slack_client_contract(self):
        """원본 PR #90의 치명 버그(get_emoji 호출부 kwarg 불일치)가 재발하지
        않도록, mock 이 아닌 실제 SlackClient 를 끼워 계약을 고정한다."""
        mock_web_client = MagicMock()
        mock_web_client.reactions_get.return_value = {
            "message": {
                "reactions": [{"name": "gogo", "users": ["U01BN035Y6L"], "count": 1}]
            }
        }

        self.run_backfill(slack=SlackClient(MagicMock(), mock_web_client))

        mock_web_client.reactions_get.assert_called_once_with(
            channel=CHANNEL, timestamp=THREAD_TS, full=True
        )
        self.sheets.append_row_if_absent.assert_called_once()
        mock_web_client.chat_postMessage.assert_called_once()  # 일괄 등록 안내
        mock_web_client.chat_postEphemeral.assert_called_once()
