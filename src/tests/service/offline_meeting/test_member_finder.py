import unittest
from unittest.mock import Mock

from exception import RuntimeException
from service.offline_meeting.member_finder import MemberFinder
from service.offline_meeting.member import Member


class MemberFinderInfoValidationTest(unittest.TestCase):
    def _create_member(self):
        return Member("문성혁", "Moon SeongHyeok", "roeniss2@gmail.com", "010-9003-4431", "토스페이먼츠")

    def _create_raw_members(self, m: Member):
        return [[], ["U1234567890", m.kor_name, m.eng_name, m.email, m.phone, m.school_name_or_company_name]]

    def _run_with_imperfect_member_info(self, member: Member):
        mock_gs_client = Mock()
        mock_gs_client.get_values.return_value = self._create_raw_members(member)

        sut = MemberFinder(mock_gs_client)

        with self.assertRaises(RuntimeException) as ex:
            sut.find('U1234567890')
        self.assertEqual(ex.exception.message, f"멤버 정보가 완벽하지 않아요. (slack_unique_id: U1234567890, member_info: {member})")

    def test_success_with_member_with_full_info(self):
        member = self._create_member()
        mock_gs_client = Mock()
        mock_gs_client.get_values.return_value = self._create_raw_members(member)

        sut = MemberFinder(mock_gs_client)

        found_member = sut.find('U1234567890')

        assert found_member == member

    def test_fail_with_member_without_kor_name(self):
        member = self._create_member()
        member.kor_name = None
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_without_eng_name(self):
        member = self._create_member()
        member.eng_name = None
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_without_email(self):
        member = self._create_member()
        member.email = None
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_without_phone(self):
        member = self._create_member()
        member.phone = None
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_without_school_name_or_company_name(self):
        member = self._create_member()
        member.school_name_or_company_name = None
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_with_empty_kor_name(self):
        member = self._create_member()
        member.kor_name = ""
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_with_empty_eng_name(self):
        member = self._create_member()
        member.eng_name = ""
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_with_empty_email(self):
        member = self._create_member()
        member.email = ""
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_with_empty_phone(self):
        member = self._create_member()
        member.phone = ""
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_with_empty_school_name_or_company_name(self):
        member = self._create_member()
        member.school_name_or_company_name = ""
        self._run_with_imperfect_member_info(member)

    def test_fail_with_member_with_improper_phone(self):
        member = self._create_member()
        member.phone = "010900034431"
        self._run_with_imperfect_member_info(member)

    def test_fail_without_target_member(self):
        mock_gs_client = Mock()
        mock_gs_client.get_values.return_value = []

        sut = MemberFinder(mock_gs_client)

        with self.assertRaises(RuntimeException) as ex:
            sut.find('U1234567890')
        self.assertEqual(ex.exception.message, f"멤버 정보를 찾지 못했어요. (slack_unique_id: U1234567890)")

    def test_fail_with_insufficient_member_info(self):
        mock_gs_client = Mock()
        mock_gs_client.get_values.return_value = [[], ["U12345890", "문성혁"]]

        sut = MemberFinder(mock_gs_client)

        with self.assertRaises(RuntimeException) as ex:
            sut.find('U1234567890')
        self.assertEqual(ex.exception.message, f"멤버 정보를 찾지 못했어요. (slack_unique_id: U1234567890)")
