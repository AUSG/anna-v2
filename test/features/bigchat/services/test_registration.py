"""참여 반응을 신청 시트 행으로 옮기는 서비스. Slack 답글은 features/bigchat/slack.py 가 맡는다."""

from unittest.mock import MagicMock

import pytest

from features.bigchat.models import Registration, RegistrationStatus
from features.bigchat.services.registration import register_applicant
from features.members.ports import MemberDirectory
from shared.gateways import AppendOutcome, SheetsGateway
from test.fixtures.slack_events import create_sample_member

USER_ID = "UQJ8HQJG5"
WORKSHEET_ID = 161837744
MEMBER = create_sample_member()
ROW = ["김동주", "school_name_or_company_name", "email@example.com", "010-1234-5678"]


@pytest.fixture
def members():
    directory = MagicMock(spec=MemberDirectory)
    directory.find.return_value = MEMBER
    return directory


@pytest.fixture
def sheets():
    gateway = MagicMock(spec=SheetsGateway)
    gateway.append_row_if_absent.return_value = AppendOutcome.ADDED
    return gateway


def test_registers_member_row_in_the_worksheet(members, sheets):
    registration = register_applicant(USER_ID, WORKSHEET_ID, members, sheets)

    assert registration == Registration(RegistrationStatus.REGISTERED, MEMBER)
    members.find.assert_called_once_with(USER_ID)
    sheets.append_row_if_absent.assert_called_once_with(WORKSHEET_ID, ROW)


def test_unknown_member_stops_before_touching_the_sheet(members, sheets):
    members.find.return_value = None

    registration = register_applicant(USER_ID, WORKSHEET_ID, members, sheets)

    assert registration == Registration(RegistrationStatus.MEMBER_NOT_FOUND)
    assert sheets.mock_calls == []


@pytest.mark.parametrize(
    "incomplete",
    [
        create_sample_member(phone="phone"),  # 13자가 아닌 전화번호
        create_sample_member(email=""),
        create_sample_member(kor_name=""),
        create_sample_member(eng_name=""),
        create_sample_member(school_name_or_company_name=""),
    ],
)
def test_member_lacking_info_stops_before_touching_the_sheet(
    members, sheets, incomplete
):
    members.find.return_value = incomplete

    registration = register_applicant(USER_ID, WORKSHEET_ID, members, sheets)

    assert registration == Registration(RegistrationStatus.MEMBER_LACKS_INFO)
    assert sheets.mock_calls == []


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (AppendOutcome.ADDED, Registration(RegistrationStatus.REGISTERED, MEMBER)),
        # 시트 생성 직후의 일괄 등록과 동시에 처리됐거나 이벤트가 중복 전달된 경우
        (
            AppendOutcome.ALREADY_PRESENT,
            Registration(RegistrationStatus.ALREADY_REGISTERED, MEMBER),
        ),
        # 시트가 이미 삭제된 경우
        (
            AppendOutcome.WORKSHEET_MISSING,
            Registration(RegistrationStatus.WORKSHEET_MISSING),
        ),
    ],
)
def test_append_outcome_maps_to_registration(members, sheets, outcome, expected):
    sheets.append_row_if_absent.return_value = outcome

    assert register_applicant(USER_ID, WORKSHEET_ID, members, sheets) == expected
    sheets.append_row_if_absent.assert_called_once_with(WORKSHEET_ID, ROW)


def test_lookup_failures_are_not_swallowed(members, sheets):
    """스프레드시트 접속 실패 같은 장애는 값이 아니라 예외로 올라가 오류 경계가 알린다."""
    members.find.side_effect = RuntimeError("스프레드시트 접속 실패")

    with pytest.raises(RuntimeError, match="스프레드시트 접속 실패"):
        register_applicant(USER_ID, WORKSHEET_ID, members, sheets)

    assert sheets.mock_calls == []
