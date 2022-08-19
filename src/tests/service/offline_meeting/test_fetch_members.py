from unittest import mock

from tests.util import add_dummy_envs
add_dummy_envs()

from service.offline_meeting.member_finder import fetch_members
from service.offline_meeting import Member


def test_success_with_empty_data():
    mock_gs_client = mock.Mock()
    mock_gs_client.get_values.return_value = [[]]

    members = fetch_members(mock_gs_client)
    assert len(members) == 0


def test_success_with_lack_info_data():
    mock_gs_client = mock.Mock()
    mock_gs_client.get_values.return_value = [
        ["user_id", "kor_name", "eng_name", "email", "phone", "school_name_or_company_name"],
        ["123", "이름", "name", "e@ma.il"]]

    members = fetch_members(mock_gs_client)
    assert len(members) == 0

def test_success_with_one_member_data():
    mock_gs_client = mock.Mock()
    mock_gs_client.get_values.return_value = [
        ["user_id", "kor_name", "eng_name", "email", "phone", "school_name_or_company_name"],
        ["123", "이름", "name", "e@ma.il", "010-1234-5678", "우리학교"]]

    members = fetch_members(mock_gs_client)
    assert len(members) == 1
    member = members.get("123")
    assert type(member) == Member
    assert (member.kor_name == "이름" and
            member.eng_name == "name" and
            member.email == "e@ma.il" and
            member.phone == "010-1234-5678" and
            member.school_name_or_company_name == "우리학교")

def test_success_with_two_member_data():
    mock_gs_client = mock.Mock()
    mock_gs_client.get_values.return_value = [
        ["user_id", "kor_name", "eng_name", "email", "phone", "school_name_or_company_name"],
        ["123", "이름", "name", "e@ma.il", "010-1234-5678", "우리학교"],
        ["456", "이름1", "name1", "e@ma.il1", "010-1234-5671", "우리학교1"]]

    members = fetch_members(mock_gs_client)
    assert len(members) == 2
    member = members.get("123")
    assert type(member) == Member
    assert (member.kor_name == "이름" and
            member.eng_name == "name" and
            member.email == "e@ma.il" and
            member.phone == "010-1234-5678" and
            member.school_name_or_company_name == "우리학교")
    member = members.get("456")
    assert (member.kor_name == "이름1" and
            member.eng_name == "name1" and
            member.email == "e@ma.il1" and
            member.phone == "010-1234-5671" and
            member.school_name_or_company_name == "우리학교1")
