from tests.util import add_dummy_envs

add_dummy_envs()

from service.offline_meeting.member_finder import validate_member_info
from service.offline_meeting import Member


def _create_member():
    return Member("문성혁", "Moon SeongHyeok", "roeniss2@gmail.com", "010-9003-4431", "토스페이먼츠")


def test_false_with_member_without_kor_name():
    member = _create_member()
    member.kor_name = None
    assert validate_member_info(member) is False


def test_false_with_member_without_eng_name():
    member = _create_member()
    member.eng_name = None
    assert validate_member_info(member) is False


def test_false_with_member_without_email():
    member = _create_member()
    member.email = None
    assert validate_member_info(member) is False


def test_false_with_member_without_phone():
    member = _create_member()
    member.phone = None
    assert validate_member_info(member) is False


def test_false_with_member_without_school_name_or_company_name():
    member = _create_member()
    member.school_name_or_company_name = None
    assert validate_member_info(member) is False


def test_false_with_member_with_empty_kor_name():
    member = _create_member()
    member.kor_name = ""
    assert validate_member_info(member) is False


def test_false_with_member_with_empty_eng_name():
    member = _create_member()
    member.eng_name = ""
    assert validate_member_info(member) is False


def test_false_with_member_with_empty_email():
    member = _create_member()
    member.email = ""
    assert validate_member_info(member) is False


def test_false_with_member_with_empty_phone():
    member = _create_member()
    member.phone = ""
    assert validate_member_info(member) is False


def test_false_with_member_with_empty_school_name_or_company_name():
    member = _create_member()
    member.school_name_or_company_name = ""
    assert validate_member_info(member) is False


def test_false_with_member_with_improper_phone():
    member = _create_member()
    member.phone = "010900034431"
    assert validate_member_info(member) is False


def test_true_with_member_with_full_info():
    member = _create_member()
    assert validate_member_info(member) is True
