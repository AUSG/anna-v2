from unittest.mock import patch

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

def test_fail_when_member_not_found():
    with patch('service.offline_meeting.member_finder.fetch_members') as mock_fetch_members:
        mock_fetch_members.return_value = {}

        assert find_member(None, "12345") is None
