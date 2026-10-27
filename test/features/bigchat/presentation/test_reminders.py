from datetime import date, datetime
from types import SimpleNamespace

import pytest

from features.bigchat.models import ReminderResult
from features.bigchat.presentation.reminders import (
    USAGE,
    build_reminder,
    build_report,
    missing_targets_message,
)
from shared.time import KST
from features.bigchat.models import BigchatEvent

NO_EVENTS_REPORT = (
    "2026-08-20 에 시작하는 빅챗을 못 찾았어. 그래서 보낼 것도 없었어.\n"
    "- 빅챗 이름 형식(`<이름> yy-MM-DD HH:mm~HH:mm`)으로 읽힌 시트: 3개\n"
    "- 형식이 안 맞아서 무시한 시트: 7개\n"
    "시트 이름이 이 형식인지 확인해줘! 자세한 목록은 로그에 남겼어."
)


def _event(name, day=20, start_hour=19, end_hour=21):
    return BigchatEvent(
        name,
        datetime(2026, 8, day, start_hour, tzinfo=KST),
        datetime(2026, 8, day, end_hour, tzinfo=KST),
    )


def _result(**overrides):
    return ReminderResult(target_date=date(2026, 8, 20), **overrides)


@pytest.mark.parametrize(
    ("name", "subject", "start_hour", "end_hour", "hours"),
    [
        ("AI 밋업", "*AI 밋업* 빅챗", 19, 21, "19:00~21:00"),
        ("빅챗", "*빅챗*", 19, 21, "19:00~21:00"),
        ("🍀 café 한글 빅챗", "*🍀 café 한글 빅챗*", 19, 21, "19:00~21:00"),
        ("빅챗 ", "*빅챗 * 빅챗", 19, 21, "19:00~21:00"),
        ("저녁 빅챗", "*저녁 빅챗*", 19, 21, "19:00~21:00"),
        ("오전 빅챗", "*오전 빅챗*", 10, 12, "10:00~12:00"),
    ],
)
def test_build_reminder_exact_message(name, subject, start_hour, end_hour, hours):
    assert build_reminder(_event(name, start_hour=start_hour, end_hour=end_hour)) == (
        f":wave: 안녕! 내일 {subject}이 열리는 날이야.\n"
        f":calendar: 8월 20일 (목) {hours}\n"
        "잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"
    )


@pytest.mark.parametrize(
    ("day", "weekday"),
    [(17, "월"), (18, "화"), (19, "수"), (20, "목"), (21, "금"), (22, "토"), (23, "일")],
)
def test_build_reminder_weekdays(day, weekday):
    assert build_reminder(_event("빅챗", day)) == (
        ":wave: 안녕! 내일 *빅챗*이 열리는 날이야.\n"
        f":calendar: 8월 {day}일 ({weekday}) 19:00~21:00\n"
        "잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"
    )


@pytest.mark.parametrize(
    "separator",
    [
        "\n",
        "\r",
        "\r\n",
        "\v",
        "\f",
        "\x1c",
        "\x1d",
        "\x1e",
        "\x85",
        "\u2028",
        "\u2029",
    ],
)
def test_build_reminder_keeps_original_literal_indentation_for_internal_lines(
    separator,
):
    assert build_reminder(_event(f"첫{separator}둘")) == (
        "            :wave: 안녕! 내일 *첫\n"
        "둘* 빅챗이 열리는 날이야.\n"
        "            :calendar: 8월 20일 (목) 19:00~21:00\n"
        "            잊지 말고 꼭 와줘! 내일 만나 :raised_hands:"
    )


@pytest.mark.parametrize("targets", [None, [], ["U1"]])
def test_build_report_no_events(targets):
    result = _result(
        bigchat_names=[],
        parsed_sheet_cnt=3,
        ignored_sheet_cnt=7,
        applicant_cnt=9,
        resolved_cnt=4,
        sent_cnt=1,
    )
    assert build_report(result, targets) == NO_EVENTS_REPORT


def test_build_report_no_events_does_not_access_applicant_or_delivery_fields():
    result = SimpleNamespace(
        target_date=date(2026, 8, 20),
        bigchat_names=[],
        parsed_sheet_cnt=3,
        ignored_sheet_cnt=7,
    )
    assert build_report(result, None) == NO_EVENTS_REPORT


def test_build_report_broadcast_without_unresolved_applicants():
    result = _result(
        bigchat_names=["빅챗", "🍀 café"],
        parsed_sheet_cnt=2,
        applicant_cnt=4,
        resolved_cnt=4,
        sent_cnt=3,
    )
    assert build_report(result, None) == (
        "2026-08-20 빅챗 `빅챗, 🍀 café` 신청자들에게 리마인더를 보냈어!\n"
        "- 신청 시트에서 찾은 신청자: 4명\n"
        "- 실제로 DM 을 보낸 사람: 3명"
    )


@pytest.mark.parametrize(
    ("applicant_cnt", "resolved_cnt", "sent_cnt", "unresolved_cnt", "parsed_sheet_cnt"),
    [(5, 3, 2, 2, 1), (2, 1, 1, 1, 0)],
)
def test_build_report_broadcast_preserves_indentation_before_unresolved_note(
    applicant_cnt, resolved_cnt, sent_cnt, unresolved_cnt, parsed_sheet_cnt
):
    result = _result(
        bigchat_names=["빅챗"],
        parsed_sheet_cnt=parsed_sheet_cnt,
        applicant_cnt=applicant_cnt,
        resolved_cnt=resolved_cnt,
        sent_cnt=sent_cnt,
    )
    assert build_report(result, None) == (
        "                2026-08-20 빅챗 `빅챗` 신청자들에게 리마인더를 보냈어!\n"
        f"                - 신청 시트에서 찾은 신청자: {applicant_cnt}명\n"
        f"                - 실제로 DM 을 보낸 사람: {sent_cnt}명\n"
        f"신청자 {unresolved_cnt}명은 멤버 시트에서 슬랙 계정을 못 찾아서 못 보냈어. (누군지는 로그에 남겼어!)"
    )


@pytest.mark.parametrize(
    ("targets", "target_text"),
    [([], ""), (["U1", "U1", "U2"], "<@U1>, <@U1>, <@U2>")],
)
def test_build_report_test_targets_keep_empty_list_and_duplicates(targets, target_text):
    result = _result(
        bigchat_names=["AI 밋업"],
        parsed_sheet_cnt=1,
        applicant_cnt=5,
        resolved_cnt=4,
        sent_cnt=2,
    )
    assert build_report(result, targets) == (
        "2026-08-20 빅챗 `AI 밋업` 찾았어!\n"
        f"테스트 DM 을 {target_text} 에게 보냈어 (2건).\n"
        "실제 발송이었다면 이렇게 나갔을 거야:\n"
        "- 신청 시트에서 찾은 신청자: 5명\n"
        "- 그 중 멤버 시트에서 슬랙 계정을 찾은 사람: 4명\n"
        "(둘이 다르면 신청 시트 이메일과 멤버 시트 이메일이 안 맞는 거야. 로그에 누군지 남겼어!)"
    )


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\u2028", "\u2029", "\x85"])
def test_build_report_broadcast_keeps_internal_name_lines(separator):
    result = _result(
        bigchat_names=[f"첫{separator}둘"],
        parsed_sheet_cnt=1,
        applicant_cnt=1,
        resolved_cnt=1,
        sent_cnt=1,
    )
    assert build_report(result, None) == (
        "                2026-08-20 빅챗 `첫\n"
        "둘` 신청자들에게 리마인더를 보냈어!\n"
        "                - 신청 시트에서 찾은 신청자: 1명\n"
        "                - 실제로 DM 을 보낸 사람: 1명"
    )


def test_build_report_test_mode_keeps_internal_name_lines():
    result = _result(
        bigchat_names=["첫\u2028둘"],
        parsed_sheet_cnt=1,
        applicant_cnt=1,
        resolved_cnt=1,
        sent_cnt=1,
    )
    assert build_report(result, ["U1"]) == (
        "            2026-08-20 빅챗 `첫\n"
        "둘` 찾았어!\n"
        "            테스트 DM 을 <@U1> 에게 보냈어 (1건).\n"
        "            실제 발송이었다면 이렇게 나갔을 거야:\n"
        "            - 신청 시트에서 찾은 신청자: 1명\n"
        "            - 그 중 멤버 시트에서 슬랙 계정을 찾은 사람: 1명\n"
        "            (둘이 다르면 신청 시트 이메일과 멤버 시트 이메일이 안 맞는 거야. 로그에 누군지 남겼어!)"
    )


@pytest.mark.parametrize("user", ["U1", "U01BN035Y6L"])
def test_missing_targets_message(user):
    assert missing_targets_message(user) == (
        "받을 사람을 같이 멘션해줘! 실수로 신청자 전원에게 나가지 않게 대상 지정을 필수로 해뒀어.\n"
        f"예) `빅챗 리마인더 테스트 <@{user}>`\n"
        "(진짜로 전원에게 보내려면 `빅챗 리마인더 지금 전원 발송` 라고 해줘!)"
    )


def test_missing_targets_message_keeps_internal_user_lines():
    assert missing_targets_message("첫\u2028둘") == (
        "                    받을 사람을 같이 멘션해줘! 실수로 신청자 전원에게 나가지 않게 대상 지정을 필수로 해뒀어.\n"
        "                    예) `빅챗 리마인더 테스트 <@첫\n"
        "둘>`\n"
        "                    (진짜로 전원에게 보내려면 `빅챗 리마인더 지금 전원 발송` 라고 해줘!)"
    )


def test_usage():
    assert USAGE == (
        "빅챗 리마인더를 저녁 6시까지 기다리지 않고 지금 돌릴 수 있어.\n"
        "- `빅챗 리마인더 테스트 @받을사람`: 멘션한 사람에게만 보내볼게 (발송이 되는지 확인용)\n"
        "- `빅챗 리마인더 지금 전원 발송`: 내일 빅챗 신청자 *전원*에게 진짜로 보낼게"
    )
