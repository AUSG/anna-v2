"""빅챗 멘션 명령의 문자열 해석. 외부 호출 없이 문법만 검증한다."""

import pytest

from features.bigchat.services.commands import (
    CreateBigchat,
    Reminder,
    is_create_bigchat,
    is_reminder,
    parse_create_bigchat,
    parse_reminder,
)

ANNA_ID = "UANNA"


class TestParseCreateBigchat:
    def test_takes_the_text_after_the_trigger(self):
        assert parse_create_bigchat(
            "<@UANNA> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        ) == CreateBigchat("AI 밋업 26-08-20 19:00~21:00")

    def test_multiline_mention_takes_only_the_first_line(self):
        text = "<@UANNA> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00\n이번 빅챗 소개글입니다\n둘째 줄"

        assert parse_create_bigchat(text) == CreateBigchat("AI 밋업 26-08-20 19:00~21:00")

    def test_mentions_after_the_trigger_are_stripped(self):
        assert parse_create_bigchat(
            "<@UANNA> 새로운 빅챗 <@U1> AI 밋업 26-08-20 19:00~21:00 <@U2>"
        ) == CreateBigchat("AI 밋업 26-08-20 19:00~21:00")

    @pytest.mark.parametrize(
        "text", ["<@UANNA> 새로운 빅챗", "<@UANNA> 새로운 빅챗 \n\n\n\n", "<@UANNA> 새로운 빅챗   "]
    )
    def test_missing_name_yields_an_empty_sheet_name(self, text):
        # 형식 검증은 CreateBigchatCommand.parse 가 하므로 여기서는 빈 문자열을 그대로 돌려준다
        assert parse_create_bigchat(text) == CreateBigchat("")

    def test_trigger_detection(self):
        assert is_create_bigchat("<@UANNA> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00")
        assert not is_create_bigchat("<@UANNA> 빅챗 23-07-31")
        assert not is_create_bigchat("<@UANNA> 안녕")


class TestParseReminder:
    def test_trigger_detection(self):
        assert is_reminder(f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001>")
        assert is_reminder(f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송")
        assert not is_reminder(f"<@{ANNA_ID}> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00")
        assert not is_reminder(f"<@{ANNA_ID}> 안녕")

    def test_broadcast_phrase(self):
        assert parse_reminder(f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송", ANNA_ID) == Reminder(
            "broadcast"
        )

    def test_broadcast_ignores_mentioned_users(self):
        """전원 발송에 사람을 같이 멘션해도 전원 발송이다 (문구가 명시적이라 그게 의도)."""
        assert parse_reminder(
            f"<@{ANNA_ID}> 빅챗 리마인더 지금 전원 발송 <@U0001>", ANNA_ID
        ) == Reminder("broadcast", ())

    def test_broadcast_takes_precedence_over_test_phrase(self):
        assert parse_reminder(
            f"<@{ANNA_ID}> 빅챗 리마인더 테스트 지금 전원 발송 <@U1>", ANNA_ID
        ) == Reminder("broadcast")

    def test_partial_phrase_does_not_broadcast(self):
        """'전원 발송' 만으로는 안 되고 문구를 통째로 쳐야 한다."""
        assert parse_reminder(f"<@{ANNA_ID}> 빅챗 리마인더 전원 발송", ANNA_ID) == Reminder(
            "usage"
        )

    def test_test_phrase_collects_mentioned_users_except_anna(self):
        assert parse_reminder(
            f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U0001> <@U0002>", ANNA_ID
        ) == Reminder("test", ("U0001", "U0002"))

    def test_test_phrase_without_targets(self):
        assert parse_reminder(f"<@{ANNA_ID}> 빅챗 리마인더 테스트", ANNA_ID) == Reminder(
            "test", ()
        )

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                f"<@{ANNA_ID}> 빅챗 리마인더 테스트 <@U1><@U1> <@U01BN035Y6L> <@{ANNA_ID}> <@lower>",
                ("U1", "U1", "U01BN035Y6L"),
            ),
            (
                "<@UANNA> 테스트 <@U1><@U1> <@UINVOKER> <@UANNA> <@lower> <@U_2> <@U3|이름> <@A9>",
                ("U1", "U1", "UINVOKER", "A9"),
            ),
        ],
    )
    def test_targets_keep_duplicates_and_invoker(self, text, expected):
        assert parse_reminder(text, ANNA_ID) == Reminder("test", expected)

    def test_usage_without_a_mode(self):
        assert parse_reminder(f"<@{ANNA_ID}> 빅챗 리마인더", ANNA_ID) == Reminder("usage")
