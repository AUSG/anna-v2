"""참여 반응이 사라지면 신청 시트의 행을 지우는 서비스. Slack 답글은 features/bigchat/slack.py 가 맡는다."""

from unittest.mock import MagicMock

import pytest

from features.bigchat.models import CancellationStatus
from features.bigchat.services.cancellation import cancel_registration
from features.members.ports import MemberDirectory
from shared.gateways import SheetsGateway
from test.fixtures.slack_events import create_sample_member

USER_ID = "UQJ8HQJG5"
WORKSHEET_ID = 161837744
MEMBER = create_sample_member()


@pytest.fixture
def members():
    directory = MagicMock(spec=MemberDirectory)
    directory.find.return_value = MEMBER
    return directory


@pytest.fixture
def sheets():
    gateway = MagicMock(spec=SheetsGateway)
    gateway.delete_row.return_value = True
    return gateway


def test_deletes_the_member_row_by_email(members, sheets):
    status = cancel_registration(USER_ID, WORKSHEET_ID, members, sheets)

    assert status is CancellationStatus.CANCELLED
    members.find.assert_called_once_with(USER_ID)
    sheets.delete_row.assert_called_once_with(WORKSHEET_ID, MEMBER.email)


def test_unknown_member_stops_before_touching_the_sheet(members, sheets):
    members.find.return_value = None

    assert (
        cancel_registration(USER_ID, WORKSHEET_ID, members, sheets)
        is CancellationStatus.MEMBER_NOT_FOUND
    )
    assert sheets.mock_calls == []


@pytest.mark.parametrize(
    "incomplete",
    [create_sample_member(phone="phone"), create_sample_member(email="")],
)
def test_member_lacking_info_stops_before_touching_the_sheet(
    members, sheets, incomplete
):
    members.find.return_value = incomplete

    assert (
        cancel_registration(USER_ID, WORKSHEET_ID, members, sheets)
        is CancellationStatus.MEMBER_LACKS_INFO
    )
    assert sheets.mock_calls == []


def test_deleted_sheet_is_reported_as_missing(members, sheets):
    sheets.delete_row.return_value = False

    assert (
        cancel_registration(USER_ID, WORKSHEET_ID, members, sheets)
        is CancellationStatus.WORKSHEET_MISSING
    )
    sheets.delete_row.assert_called_once_with(WORKSHEET_ID, MEMBER.email)


def test_lookup_failures_are_not_swallowed(members, sheets):
    members.find.side_effect = RuntimeError("스프레드시트 접속 실패")

    with pytest.raises(RuntimeError, match="스프레드시트 접속 실패"):
        cancel_registration(USER_ID, WORKSHEET_ID, members, sheets)

    assert sheets.mock_calls == []
