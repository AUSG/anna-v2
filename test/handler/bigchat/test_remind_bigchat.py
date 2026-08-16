import unittest
from datetime import datetime
from unittest.mock import MagicMock

from dateutil.tz import gettz

from handler.bigchat.remind_bigchat import RemindBigchat

KST = gettz("Asia/Seoul")

# 행사(26-08-20 목요일) 전날 저녁 8시
NOW = datetime(2026, 8, 19, 20, 0, tzinfo=KST)


class TestRemindBigchat(unittest.TestCase):
    def setUp(self):
        self.mock_slack_client = MagicMock()
        self.mock_gs_client = MagicMock()
        self.mock_member_manager = MagicMock()
        self.sut = RemindBigchat(
            self.mock_slack_client, self.mock_gs_client, self.mock_member_manager
        )

    def test_run_sends_dm_to_all_applicants_of_tomorrow_bigchat(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "AI 밋업 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            [],  # 시트 생성 시 들어가는 빈 헤더 행
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],
            ["박영희", "AUSG사", " YoungHee@Example.com ", "010-2345-6789"],  # 대소문자/공백
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
            "younghee@example.com": "U0002",
        }

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 2
        dm_calls = self.mock_slack_client.send_direct_message.call_args_list
        assert [c.kwargs["user_id"] for c in dm_calls] == ["U0001", "U0002"]
        msg = dm_calls[0].kwargs["msg"]
        assert "내일" in msg
        assert "AI 밋업" in msg
        assert "8월 20일 (목) 19:00~21:00" in msg

    def test_run_skips_sheets_not_happening_tomorrow(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (1, "오늘 빅챗 26-08-19 19:00~21:00"),
            (2, "모레 빅챗 26-08-21 19:00~21:00"),
            (3, "빅챗 23-07-31"),  # 구형식 시트
            (4, "MEMBERS_INFO"),  # 빅챗이 아닌 시트
        ]

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 0
        self.mock_gs_client.get_values.assert_not_called()
        self.mock_slack_client.send_direct_message.assert_not_called()

    def test_run_reminds_every_bigchat_of_tomorrow(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (1, "오전 빅챗 26-08-20 10:00~12:00"),
            (2, "저녁 빅챗 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
        }

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 2  # 두 빅챗 모두에 신청했으니 DM 도 두 번

    def test_run_skips_applicant_not_in_members_sheet(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "AI 밋업 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],
            ["외부인", "게스트", "guest@example.com", "010-0000-0000"],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
        }

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 1
        self.mock_slack_client.send_direct_message.assert_called_once()
        assert (
            self.mock_slack_client.send_direct_message.call_args.kwargs["user_id"]
            == "U0001"
        )

    def test_run_picks_email_cell_even_when_company_name_contains_at(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "AI 밋업 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            # 소속에 '@' 가 들어가도 이메일 셀을 집어야 한다
            ["김철수", "@drama&company", "chulsoo@example.com", "010-1234-5678"],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
        }

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 1
        assert (
            self.mock_slack_client.send_direct_message.call_args.kwargs["user_id"]
            == "U0001"
        )

    def test_run_dedups_duplicated_application(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "AI 밋업 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],  # 중복 신청
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
        }

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 1
        self.mock_slack_client.send_direct_message.assert_called_once()

    def test_run_continues_when_one_dm_fails(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "AI 밋업 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],
            ["박영희", "AUSG사", "younghee@example.com", "010-2345-6789"],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
            "younghee@example.com": "U0002",
        }
        self.mock_slack_client.send_direct_message.side_effect = [
            Exception("account_inactive"),
            None,
        ]

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 1  # 첫 DM 실패해도 두 번째는 발송된다
        assert self.mock_slack_client.send_direct_message.call_count == 2

    def test_run_with_no_bigchat_tomorrow(self):
        self.mock_gs_client.list_worksheets.return_value = []

        sent_cnt = self.sut.run(now=NOW)

        assert sent_cnt == 0
        self.mock_slack_client.send_direct_message.assert_not_called()
