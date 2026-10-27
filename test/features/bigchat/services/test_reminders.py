import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from features.bigchat.models import BigchatEvent, ReminderResult
from features.bigchat.presentation.reminders import build_reminder
from features.bigchat.services.reminders import RemindBigchat
from features.members.ports import MemberDirectory
from shared.gateways import SheetsGateway, SlackGateway
from shared.time import KST

# 행사(26-08-20 목요일) 전날 저녁 6시
NOW = datetime(2026, 8, 19, 18, 0, tzinfo=KST)


def _dm_user_ids(slack):
    return [c.args[0] for c in slack.send_direct_message.call_args_list]


class RemindBigchatTestBase(unittest.TestCase):
    def setUp(self):
        self.mock_slack_client = MagicMock(spec=SlackGateway)
        self.mock_gs_client = MagicMock(spec=SheetsGateway)
        self.mock_member_manager = MagicMock(spec=MemberDirectory)
        self.sut = RemindBigchat(
            self.mock_slack_client, self.mock_gs_client, self.mock_member_manager
        )


class TestRemindBigchat(RemindBigchatTestBase):
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

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 2
        dm_calls = self.mock_slack_client.send_direct_message.call_args_list
        assert [c.args[0] for c in dm_calls] == ["U0001", "U0002"]
        msg = dm_calls[0].args[1]
        assert "내일" in msg
        assert "*AI 밋업* 빅챗이 열리는 날이야" in msg
        assert "8월 20일 (목) 19:00~21:00" in msg

    def test_message_does_not_repeat_bigchat_when_name_already_ends_with_it(self):
        """시트를 '빅챗 26-08-20 ...' 로 만들면 이름이 그냥 '빅챗' 이라 '*빅챗* 빅챗이' 로 겹쳤다."""
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "빅챗 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = [
            ["김철수", "AUSG대", "chulsoo@example.com", "010-1234-5678"],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "chulsoo@example.com": "U0001",
        }

        self.sut.run(now=NOW)

        msg = self.mock_slack_client.send_direct_message.call_args.args[1]
        assert "*빅챗*이 열리는 날이야" in msg
        assert "빅챗 빅챗" not in msg

    def test_run_skips_sheets_not_happening_tomorrow(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (1, "오늘 빅챗 26-08-19 19:00~21:00"),
            (2, "모레 빅챗 26-08-21 19:00~21:00"),
            (3, "빅챗 23-07-31"),  # 구형식 시트
            (4, "MEMBERS_INFO"),  # 빅챗이 아닌 시트
        ]

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 0
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

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 2  # 두 빅챗 모두에 신청했으니 DM 도 두 번

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

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 1
        self.mock_slack_client.send_direct_message.assert_called_once()
        assert self.mock_slack_client.send_direct_message.call_args.args[0] == "U0001"

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

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 1
        assert self.mock_slack_client.send_direct_message.call_args.args[0] == "U0001"

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

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 1
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

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 1  # 첫 DM 실패해도 두 번째는 발송된다
        assert self.mock_slack_client.send_direct_message.call_count == 2

    def test_run_with_no_bigchat_tomorrow(self):
        self.mock_gs_client.list_worksheets.return_value = []

        result = self.sut.run(now=NOW)

        assert result.sent_cnt == 0
        self.mock_slack_client.send_direct_message.assert_not_called()

    def test_result_summarizes_sheet_scan(self):
        """왜 아무것도 안 보냈는지 로그/응답으로 판단할 수 있어야 한다."""
        self.mock_gs_client.list_worksheets.return_value = [
            (1, "모레 빅챗 26-08-21 19:00~21:00"),  # 형식은 맞지만 내일이 아님
            (2, "빅챗 23-07-31"),  # 구형식 -> 무시
            (3, "MEMBERS_INFO"),  # 빅챗 시트 아님 -> 무시
        ]

        result = self.sut.run(now=NOW)

        assert result.bigchat_names == []
        assert result.target_date.isoformat() == "2026-08-20"
        assert result.parsed_sheet_cnt == 1
        assert result.ignored_sheet_cnt == 2


class TestRemindBigchatTestMode(RemindBigchatTestBase):
    """only_user_ids 를 주면 신청자 대신 지정한 사람에게만 간다 (수동 트리거)."""

    def setUp(self):
        super().setUp()
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

    def test_sends_only_to_given_users(self):
        result = self.sut.run(now=NOW, only_user_ids=["U9999"])

        assert _dm_user_ids(self.mock_slack_client) == ["U9999"]
        assert result.sent_cnt == 1

    def test_still_reports_what_the_real_run_would_have_done(self):
        result = self.sut.run(now=NOW, only_user_ids=["U9999"])

        # 실제 신청자/매칭 집계는 테스트 모드에서도 그대로 나와야 진단에 쓸 수 있다
        assert result.applicant_cnt == 2
        assert result.resolved_cnt == 2
        assert result.bigchat_names == ["AI 밋업"]

    def test_sends_to_target_even_if_not_an_applicant(self):
        """테스트 대상이 신청자가 아니어도 DM 은 가야 한다 (발송 경로 자체를 확인하는 용도)."""
        self.mock_member_manager.email_to_slack_ids.return_value = {}

        result = self.sut.run(now=NOW, only_user_ids=["U9999"])

        assert result.sent_cnt == 1
        assert result.resolved_cnt == 0  # 신청자는 아무도 매칭 안 됐지만


class TestReminderBoundaries(RemindBigchatTestBase):
    def test_tomorrow_at_calendar_and_timezone_boundaries(self):
        for now, target in [
            (datetime(2026, 12, 31, 23, 59, 59, tzinfo=KST), date(2027, 1, 1)),
            (datetime(2028, 2, 28, 23, 59, 59, tzinfo=KST), date(2028, 2, 29)),
            (datetime(2028, 2, 29, 0, 0, tzinfo=KST), date(2028, 3, 1)),
            (datetime(2026, 8, 19, 0, 0, tzinfo=KST), date(2026, 8, 20)),
            (datetime(2026, 8, 19, 23, 59, tzinfo=timezone.utc), date(2026, 8, 20)),
            (datetime(2026, 8, 19, 23, 59), date(2026, 8, 20)),
        ]:
            with self.subTest(now=now):
                self.mock_gs_client.list_worksheets.return_value = []
                assert self.sut.run(now=now).target_date == target

    def test_default_clock_is_kst(self):
        self.mock_gs_client.list_worksheets.return_value = []
        with patch("features.bigchat.services.reminders.datetime") as clock:
            clock.now.return_value = NOW
            result = self.sut.run()
        clock.now.assert_called_once_with(KST)
        assert result.target_date == date(2026, 8, 20)

    def test_sheet_row_and_call_order_with_shared_slack_accounts(self):
        calls = MagicMock()
        calls.attach_mock(self.mock_gs_client, "sheets")
        calls.attach_mock(self.mock_member_manager, "members")
        calls.attach_mock(self.mock_slack_client, "slack")
        self.mock_gs_client.list_worksheets.return_value = [
            (22, "저녁 빅챗 26-08-20 19:00~21:00"),
            (99, "MEMBERS_INFO"),
            (11, "오전 빅챗 26-08-20 10:00~12:00"),
        ]
        self.mock_gs_client.get_values.side_effect = [
            [
                [],
                [" A@Example.com ", "unused@example.com"],
                ["b@example.com"],
                ["a@example.com"],
                ["guest@example.com"],
            ],
            [["a@example.com"]],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "a@example.com": "U1",
            "b@example.com": "U1",
        }

        result = self.sut.run(now=NOW)

        assert result == ReminderResult(
            target_date=date(2026, 8, 20),
            bigchat_names=["저녁 빅챗", "오전 빅챗"],
            parsed_sheet_cnt=2,
            ignored_sheet_cnt=1,
            applicant_cnt=4,
            resolved_cnt=3,
            sent_cnt=3,
        )
        assert [c[0] for c in calls.mock_calls] == [
            "sheets.list_worksheets",
            "members.email_to_slack_ids",
            "sheets.get_values",
            "slack.send_direct_message",
            "slack.send_direct_message",
            "members.email_to_slack_ids",
            "sheets.get_values",
            "slack.send_direct_message",
        ]
        assert [c.args for c in self.mock_gs_client.get_values.call_args_list] == [
            (22,),
            (11,),
        ]
        evening = (
            ":wave: 안녕! 내일 *저녁 빅챗*이 열리는 날이야.\n"
            ":calendar: 8월 20일 (목) 19:00~21:00\n"
            "잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"
        )
        morning = (
            ":wave: 안녕! 내일 *오전 빅챗*이 열리는 날이야.\n"
            ":calendar: 8월 20일 (목) 10:00~12:00\n"
            "잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"
        )
        assert [
            c.args for c in self.mock_slack_client.send_direct_message.call_args_list
        ] == [
            ("U1", evening),
            ("U1", evening),
            ("U1", morning),
        ]

    def test_empty_targets_still_count_applicants_without_sending(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (111, "빅챗 26-08-20 19:00~21:00")
        ]
        self.mock_gs_client.get_values.return_value = [
            ["a@example.com"],
            ["guest@example.com"],
        ]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "a@example.com": "U1"
        }

        with self.assertLogs(
            "features.bigchat.services.reminders", level="INFO"
        ) as logs:
            result = self.sut.run(now=NOW, only_user_ids=[])

        assert result.applicant_cnt == 2
        assert result.resolved_cnt == 1
        assert result.sent_cnt == 0
        self.mock_slack_client.send_direct_message.assert_not_called()
        assert "TEST MODE: sending to [] instead of the 1 resolved applicant(s)" in [
            record.getMessage() for record in logs.records
        ]
        assert "TEST MODE -> only" not in logs.records[0].getMessage()

    def test_repeated_test_targets_are_sent_for_each_bigchat_even_after_failure(self):
        self.mock_gs_client.list_worksheets.return_value = [
            (1, "첫 빅챗 26-08-20 19:00~21:00"),
            (2, "둘 빅챗 26-08-20 19:00~21:00"),
        ]
        self.mock_gs_client.get_values.return_value = []
        self.mock_member_manager.email_to_slack_ids.return_value = {}
        self.mock_slack_client.send_direct_message.side_effect = [
            RuntimeError("inactive"),
            None,
            None,
            None,
        ]

        with self.assertLogs(
            "features.bigchat.services.reminders", level="INFO"
        ) as logs:
            result = self.sut.run(now=NOW, only_user_ids=["U9", "U9"])

        assert result.applicant_cnt == result.resolved_cnt == 0
        assert result.sent_cnt == 3
        assert _dm_user_ids(self.mock_slack_client) == ["U9", "U9", "U9", "U9"]
        errors = [r for r in logs.records if r.levelname == "ERROR"]
        assert [r.getMessage() for r in errors] == ["Failed to DM U9 <?> (첫 빅챗)"]
        assert errors[0].exc_info[0] is RuntimeError

    def test_applicant_email_helper_preserves_deduplication_and_logs(self):
        self.mock_gs_client.get_values.return_value = [
            [],
            [" A@Example.com ", "unused@example.com"],
            ["a@example.com"],
            ["@company", "b@example.com"],
            ["no email"],
        ]
        with self.assertLogs(
            "features.bigchat.services.reminders", level="DEBUG"
        ) as logs:
            assert self.sut._applicant_emails(111) == ["a@example.com", "b@example.com"]
        assert [r.getMessage() for r in logs.records] == [
            "Worksheet 111: no email in row []",
            "Worksheet 111: duplicated applicant a@example.com",
            "Worksheet 111: no email in row ['no email']",
            "Worksheet 111: 5 row(s) -> 2 unique applicant email(s), 2 row(s) without an email",
        ]

    def test_account_lookups_preserve_order_case_duplicates_and_shared_accounts(self):
        emails = [
            "a@example.com",
            "missing@example.com",
            "b@example.com",
            "A@example.com",
            "a@example.com",
            "empty@example.com",
        ]
        lookups = []

        class RecordingMapping(dict):
            def get(self, email):
                slack_id = super().get(email)
                lookups.append((slack_id, email))
                return slack_id

        mapping = RecordingMapping(
            {"a@example.com": "U1", "b@example.com": "U1", "empty@example.com": ""}
        )
        self.mock_member_manager.email_to_slack_ids.return_value = mapping
        event = BigchatEvent(
            "빅챗",
            datetime(2026, 8, 20, 19, tzinfo=KST),
            datetime(2026, 8, 20, 21, tzinfo=KST),
        )
        result = ReminderResult(date(2026, 8, 20))

        with patch.object(
            self.sut, "_applicant_emails", return_value=emails
        ) as applicants:
            with self.assertLogs(
                "features.bigchat.services.reminders", level="INFO"
            ) as logs:
                assert self.sut._remind_applicants(111, event, None, result) is None

        applicants.assert_called_once_with(111)
        assert lookups == [
            ("U1", "a@example.com"),
            (None, "missing@example.com"),
            ("U1", "b@example.com"),
            (None, "A@example.com"),
            ("U1", "a@example.com"),
            ("", "empty@example.com"),
        ]
        assert mapping == {
            "a@example.com": "U1",
            "b@example.com": "U1",
            "empty@example.com": "",
        }
        assert emails[0] == "a@example.com"
        assert result == ReminderResult(
            date(2026, 8, 20), applicant_cnt=6, resolved_cnt=3, sent_cnt=3
        )
        assert _dm_user_ids(self.mock_slack_client) == ["U1", "U1", "U1"]
        assert [r.getMessage() for r in logs.records if r.levelname == "WARNING"] == [
            "Applicant not found in members sheet, skipping DM: missing@example.com (빅챗)",
            "Applicant not found in members sheet, skipping DM: A@example.com (빅챗)",
            "Applicant not found in members sheet, skipping DM: empty@example.com (빅챗)",
        ]
        assert [
            r.getMessage()
            for r in logs.records
            if r.getMessage().startswith("Sent reminder DM to ")
        ] == [
            "Sent reminder DM to U1 <a@example.com> (빅챗)",
            "Sent reminder DM to U1 <b@example.com> (빅챗)",
            "Sent reminder DM to U1 <a@example.com> (빅챗)",
        ]

    def test_mapping_failure_follows_warning_without_updating_counts_or_sending(self):
        lookups = []
        warning = "Applicant not found in members sheet, skipping DM: missing@example.com (빅챗)"

        class FailingMapping(dict):
            def get(self, email):
                lookups.append(email)
                if email == "fail@example.com":
                    assert [r.getMessage() for r in logs.records] == [warning]
                    raise ValueError("member lookup failed")
                return super().get(email)

        self.mock_member_manager.email_to_slack_ids.return_value = FailingMapping()
        event = BigchatEvent(
            "빅챗",
            datetime(2026, 8, 20, 19, tzinfo=KST),
            datetime(2026, 8, 20, 21, tzinfo=KST),
        )
        result = ReminderResult(
            date(2026, 8, 20), applicant_cnt=5, resolved_cnt=2, sent_cnt=4
        )
        with patch.object(
            self.sut,
            "_applicant_emails",
            return_value=["missing@example.com", "fail@example.com"],
        ):
            with self.assertLogs(
                "features.bigchat.services.reminders", level="WARNING"
            ) as logs:
                with self.assertRaisesRegex(ValueError, "member lookup failed"):
                    self.sut._remind_applicants(111, event, None, result)

        assert lookups == ["missing@example.com", "fail@example.com"]
        assert [r.getMessage() for r in logs.records] == [warning]
        assert result == ReminderResult(
            date(2026, 8, 20), applicant_cnt=5, resolved_cnt=2, sent_cnt=4
        )
        self.mock_slack_client.send_direct_message.assert_not_called()

    def test_invalid_row_propagates_after_prior_row_logs_without_updating_counts(self):
        event = BigchatEvent(
            "빅챗",
            datetime(2026, 8, 20, 19, tzinfo=KST),
            datetime(2026, 8, 20, 21, tzinfo=KST),
        )
        result = ReminderResult(date(2026, 8, 20))
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "a@example.com": "U1"
        }
        self.mock_gs_client.get_values.return_value = [[], ["a@example.com"], [None]]

        with self.assertLogs(
            "features.bigchat.services.reminders", level="DEBUG"
        ) as logs:
            with self.assertRaises(AttributeError):
                self.sut._remind_applicants(111, event, None, result)

        assert [r.getMessage() for r in logs.records] == [
            "Worksheet 111: no email in row []"
        ]
        assert result.applicant_cnt == result.resolved_cnt == result.sent_cnt == 0
        self.mock_slack_client.send_direct_message.assert_not_called()

    def test_invalid_sheet_title_propagates_before_scan_summary(self):
        self.mock_gs_client.list_worksheets.return_value = [(1, None)]
        with self.assertLogs(
            "features.bigchat.services.reminders", level="INFO"
        ) as logs:
            with self.assertRaises(AttributeError):
                self.sut.run(now=NOW)
        assert len(logs.records) == 1
        self.mock_member_manager.email_to_slack_ids.assert_not_called()
        self.mock_gs_client.get_values.assert_not_called()

    def test_lookup_errors_are_not_swallowed_as_dm_failures(self):
        for failing_method in [
            self.mock_gs_client.list_worksheets,
            self.mock_member_manager.email_to_slack_ids,
            self.mock_gs_client.get_values,
        ]:
            with self.subTest(method=failing_method):
                self.mock_gs_client.list_worksheets.return_value = [
                    (1, "빅챗 26-08-20 19:00~21:00")
                ]
                failing_method.side_effect = RuntimeError("lookup failed")
                with self.assertRaisesRegex(RuntimeError, "lookup failed"):
                    self.sut.run(now=NOW)
                failing_method.side_effect = None
        self.mock_slack_client.send_direct_message.assert_not_called()

    def test_dm_text_is_the_presentation_message_with_internal_unicode_line_indentation(
        self,
    ):
        """DM 본문은 presentation 의 문구를 가공 없이 그대로 보낸다 (이름 안의 줄구분자도 포함)."""
        self.mock_gs_client.list_worksheets.return_value = [
            (1, "첫 둘 26-08-20 19:00~21:00")
        ]
        self.mock_gs_client.get_values.return_value = [["a@example.com"]]
        self.mock_member_manager.email_to_slack_ids.return_value = {
            "a@example.com": "U1"
        }
        event = BigchatEvent(
            "첫 둘",
            datetime(2026, 8, 20, 19, tzinfo=KST),
            datetime(2026, 8, 20, 21, tzinfo=KST),
        )

        self.sut.run(now=NOW)

        self.mock_slack_client.send_direct_message.assert_called_once_with(
            "U1", build_reminder(event)
        )
        assert build_reminder(event) == (
            "            :wave: 안녕! 내일 *첫\n"
            "둘* 빅챗이 열리는 날이야.\n"
            "            :calendar: 8월 20일 (목) 19:00~21:00\n"
            "            잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"
        )
