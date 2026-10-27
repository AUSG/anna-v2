import pytest

from features.bigchat.models import CancellationStatus, RegistrationStatus
from features.bigchat.presentation.messages import (
    CANCELLATION_NOTICES,
    REGISTRATION_NOTICES,
    bigchat_created_message,
    build_registration_info_message,
    cancellation_notice,
    cancelled_message,
    early_reactions_failed_message,
    early_reactions_registered_message,
    registered_message,
    registration_notice,
)
from test.fixtures.slack_events import create_sample_member

USER = "UQJ8HQJG5"


# --- 참여 신청 ----------------------------------------------------------------------


def test_every_non_success_registration_status_has_a_notice():
    """성공은 registered_message 로, 나머지 모든 결과는 notice 로 안내할 수 있어야 한다."""
    assert set(REGISTRATION_NOTICES) == set(RegistrationStatus) - {
        RegistrationStatus.REGISTERED
    }


@pytest.mark.parametrize(
    ("status", "phrase"),
    [
        (RegistrationStatus.ALREADY_REGISTERED, "이미 등록되어 있어!"),
        (RegistrationStatus.MEMBER_NOT_FOUND, "네 정보를 찾지 못했어. 운영진에게 연락해줘!"),
        (RegistrationStatus.MEMBER_LACKS_INFO, "네 정보에 누락된 값이 있어. 운영진에게 연락해줘!"),
        (
            RegistrationStatus.WORKSHEET_MISSING,
            "이 빅챗의 신청 시트를 찾을 수 없어. 이미 마감되었거나 삭제된 것 같아.",
        ),
    ],
)
def test_registration_notice_mentions_the_user_and_the_outcome(status, phrase):
    notice = registration_notice(status, USER)

    assert notice.startswith(f"<@{USER}>, ")
    assert phrase in notice


def test_registration_notice_for_missing_worksheet_tells_how_to_recover():
    assert "모집이 진행 중인 빅챗이라면 운영진에게 알려줘!" in registration_notice(
        RegistrationStatus.WORKSHEET_MISSING, USER
    )


def test_registered_message():
    assert registered_message(USER) == f"<@{USER}>, 등록 완료!"


def test_registration_info_message_lists_the_registered_values_and_is_private():
    member = create_sample_member()

    msg = build_registration_info_message(USER, member)

    assert msg == (
        f"<@{USER}> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!\n"
        "```\n"
        "이름(영문): 김동주(Kim Dongjoo)\n"
        "핸드폰: 010-1234-5678\n"
        "이메일: email@example.com\n"
        "학교/회사: school_name_or_company_name\n"
        "```\n"
        "(참고로 이 메시지는 너만 볼 수 있어!)"
    )


# --- 참여 취소 ----------------------------------------------------------------------


def test_every_non_success_cancellation_status_has_a_notice():
    assert set(CANCELLATION_NOTICES) == set(CancellationStatus) - {
        CancellationStatus.CANCELLED
    }


@pytest.mark.parametrize(
    ("status", "phrase"),
    [
        (CancellationStatus.MEMBER_NOT_FOUND, "네 정보를 찾지 못했어."),
        (CancellationStatus.MEMBER_LACKS_INFO, "네 정보에 누락된 값이 있어."),
        (CancellationStatus.WORKSHEET_MISSING, "이 빅챗의 신청 시트를 찾을 수 없어서 등록을 취소하지 못했어"),
    ],
)
def test_cancellation_notice_mentions_the_user_and_the_outcome(status, phrase):
    notice = cancellation_notice(status, USER)

    assert notice.startswith(f"<@{USER}>, ")
    assert phrase in notice


def test_cancelled_message():
    assert cancelled_message(USER) == f"<@{USER}>, 등록을 취소했어."


# --- 시트 생성 전에 눌린 반응 -------------------------------------------------------


def test_bigchat_created_message_links_the_sheet():
    assert bigchat_created_message(
        "https://sheet.test/edit#gid=1", "AI 밋업 26-08-20 19:00~21:00"
    ) == (
        "새로운 빅챗, 등록 완료! <https://sheet.test/edit#gid=1|AI 밋업 26-08-20 19:00~21:00> :google_spreadsheets:"
    )


@pytest.mark.parametrize(
    ("users", "mentions"),
    [(["U1"], "<@U1>"), (["U1", "U2", "U1"], "<@U1> <@U2> <@U1>")],
)
def test_early_reactions_registered_message_mentions_everyone_in_order(users, mentions):
    assert early_reactions_registered_message(users, "gogo") == (
        f"{mentions} 시트가 만들어지기 전에 :gogo:를 눌러줬구나! 지금 등록 완료했어!"
    )


def test_early_reactions_failed_message_asks_to_check_the_sheet():
    assert early_reactions_failed_message("gogo") == " ".join(
        [
            "미리 눌린 :gogo: 자동 등록을 처리하다 문제가 생겨서 멈췄어.",
            "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!",
        ]
    )
