from unittest.mock import patch

from _pytest.python_api import raises

from exception import RuntimeException
from tests.util import add_dummy_envs

add_dummy_envs()

from service.offline_meeting.member_finder import find_member
from service.offline_meeting import Member


def _create_member():
    member = Member("이름", "eng_name", "e@ma.il", "010-1234-5678", "우리학교")
    return member


def test_success_when_member_found():
    with patch('service.offline_meeting.member_finder.fetch_members') as mock_fetch_members:
        member = _create_member()
        mock_fetch_members.return_value = {"12345": member}
        found_member = find_member(None, "12345")

        assert found_member == member


def test_fail_with_member_without_school_name_or_company_name():
    with patch('service.offline_meeting.member_finder.fetch_members') as mock_fetch_members:
        member = _create_member()
        member.school_name_or_company_name = None
        mock_fetch_members.return_value = {"12345": member}

        with raises(RuntimeException) as ex:
            find_member(None, "12345")
        assert ex.value.message == '멤버 정보가 완벽하지 않아요. (slack_unique_id: 12345, member_info: [Member] 이름 | eng_name | e@ma.il | 010-1234-5678 | None)'

def test_fail_with_member_with_incorrect_phone():
    with patch('service.offline_meeting.member_finder.fetch_members') as mock_fetch_members:
        member = _create_member()
        member.phone = '01012345678'
        mock_fetch_members.return_value = {"12345": member}

        with raises(RuntimeException) as ex:
            find_member(None, "12345")
        assert ex.value.message == '멤버 정보가 완벽하지 않아요. (slack_unique_id: 12345, member_info: [Member] 이름 | eng_name | e@ma.il | 01012345678 | 우리학교)'

def test_fail_when_member_not_found():
    with patch('service.offline_meeting.member_finder.fetch_members') as mock_fetch_members:
        mock_fetch_members.return_value = {}

        with raises(RuntimeException) as ex:
            find_member(None, "12345")
        assert ex.value.message == '멤버 정보를 찾지 못했어요. (slack_unique_id: 12345)'
