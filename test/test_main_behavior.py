"""리팩터링에서 달라졌던 경계를 main 의 실제 구현으로 고정한다."""

from unittest.mock import MagicMock

import pytest

from features.bigchat.handlers.create_bigchat_sheet import CreateBigchatSheet
from features.bigchat.services.creation import register_early_reacted_users
from features.members.services.directory import MemberManager
from features.questions.models import select_conversation
from integrations.google_sheets import GoogleSpreadsheetClient, WorksheetNotFound
from integrations.slack import Reaction
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_member,
)


@pytest.mark.parametrize("suffix", [" <@U01BN035Y6L>", " <@UOTHER>"])
def test_trailing_mention_is_not_removed_from_bigchat_name(suffix):
    event = create_sample_app_mention_event(
        "새로운 빅챗 AI 밋업 26-08-20 19:00~21:00" + suffix
    )
    slack, sheets = MagicMock(), MagicMock()
    handler = CreateBigchatSheet(event, slack, sheets, MagicMock(), "gogo")
    assert handler.handle_mention() is False
    sheets.create_bigchat_sheet.assert_not_called()
    assert (
        "형식이 올바르지 않아서"
        in slack.send_message_only_visible_to_user.call_args.kwargs["msg"]
    )


def test_member_lookup_keeps_main_two_cache_layers():
    MemberManager.find.cache_clear()
    MemberManager._fetch_members.cache_clear()
    try:
        assert MemberManager.find.cache.ttl == 600
        assert MemberManager._fetch_members.cache.ttl == 60
        sheets = MagicMock()
        rows = [
            ["user", "kor", "eng", "email", "phone", "school"],
            ["U1", "김철수", "Kim", "old@example.com", "010-1234-5678", "AUSG"],
        ]
        sheets.get_values.return_value = rows
        manager = MemberManager(sheets)
        first = manager.find("U1")
        sheets.get_values.return_value = [
            rows[0],
            [*rows[1][:3], "new@example.com", *rows[1][4:]],
        ]
        # 목록 캐시가 갱신돼도 회원별 성공 결과는 기존 600초 캐시에 남는다.
        MemberManager._fetch_members.cache_clear()
        assert manager.email_to_slack_ids() == {"new@example.com": "U1"}
        assert manager.find("U1") is first
        assert manager.find("U1").email == "old@example.com"
        MemberManager.find.cache_clear()
        assert manager.find("U1").email == "new@example.com"
    finally:
        MemberManager.find.cache_clear()
        MemberManager._fetch_members.cache_clear()


def test_conversation_selection_keeps_main_duplicate_candidate_budget():
    turns = [
        {"role": "user", "content": "무" * 4000, "timestamp": str(index)}
        for index in range(12)
    ]
    turns[11]["content"] = "Kubernetes" + "가" * 3990
    assert [turn["timestamp"] for turn in select_conversation(turns, "Kubernetes")] == [
        "0",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
    ]


def test_missing_sheet_during_early_registration_keeps_main_warning():
    slack, sheets, members = MagicMock(), MagicMock(), MagicMock()
    slack.get_emoji.return_value = Reaction(name="gogo", users=["U1"], count=1)
    members.find.return_value = create_sample_member()
    sheets.append_row_if_absent.side_effect = WorksheetNotFound()
    register_early_reacted_users(slack, sheets, members, "gogo", 1, "C1", "1.0")
    slack.send_thread_message.assert_called_once_with(
        msg="미리 눌린 :gogo: 자동 등록을 처리하다 문제가 생겨서 멈췄어. " "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!",
        channel="C1",
        ts="1.0",
    )
    slack.send_message_only_visible_to_user.assert_not_called()


def test_missing_worksheet_is_not_converted_to_empty_rows():
    sheets = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    sheets._get_worksheet = MagicMock(side_effect=WorksheetNotFound())
    with pytest.raises(WorksheetNotFound):
        sheets.get_values(123)
    sheets._get_worksheet.assert_called_once_with(123)
