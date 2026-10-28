import unittest
from unittest.mock import MagicMock

from features.members.services.directory import (
    MemberLackInfo,
    MemberManager,
    MemberNotFound,
)


class TestMemberManager(unittest.TestCase):
    def setUp(self):
        mock_gs_client = MagicMock()
        mock_gs_client.get_values.return_value = [
            ["user_id", "kor_name", "eng_name", "email", "phone", "school"],  # 헤더
            [
                "U0001",
                "김철수",
                "Kim Chulsoo",
                "Chulsoo@Example.com",
                "010-1234-5678",
                "AUSG대",
            ],
            [
                "U0002",
                "박영희",
                "Park Younghee",
                "",
                "010-2345-6789",
                "AUSG사",
            ],  # 이메일 없음
            ["U0003", "이몽룡"],  # 값 누락 행 (스킵됨)
        ]
        self.sut = MemberManager(mock_gs_client)

    def test_maps_normalized_email_to_slack_id(self):
        assert self.sut.email_to_slack_ids() == {"chulsoo@example.com": "U0001"}

    def test_finds_member_and_builds_registration_row(self):
        member = self.sut.find("U0001")  # ty: ignore[missing-argument, invalid-argument-type]

        assert member.eng_name == "Kim Chulsoo"
        assert member.transform_for_spreadsheet() == [
            "김철수",
            "AUSG대",
            "Chulsoo@Example.com",
            "010-1234-5678",
        ]

    def test_missing_member_is_reported(self):
        with self.assertRaises(MemberNotFound):
            self.sut.find("U_UNKNOWN")  # ty: ignore[missing-argument, invalid-argument-type]

    def test_incomplete_member_is_reported(self):
        with self.assertRaises(MemberLackInfo):
            self.sut.find("U0002")  # ty: ignore[missing-argument, invalid-argument-type]
