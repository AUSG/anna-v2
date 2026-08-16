import unittest
from unittest.mock import MagicMock

from implementation.member_finder import MemberManager


class TestEmailToSlackIds(unittest.TestCase):
    def test_maps_normalized_email_to_slack_id(self):
        mock_gs_client = MagicMock()
        mock_gs_client.get_values.return_value = [
            ["user_id", "kor_name", "eng_name", "email", "phone", "school"],  # 헤더
            ["U0001", "김철수", "Kim Chulsoo", "Chulsoo@Example.com", "010-1234-5678", "AUSG대"],
            ["U0002", "박영희", "Park Younghee", "", "010-2345-6789", "AUSG사"],  # 이메일 없음
            ["U0003", "이몽룡"],  # 값 누락 행 (스킵됨)
        ]
        sut = MemberManager(mock_gs_client)

        mapping = sut.email_to_slack_ids()

        assert mapping == {"chulsoo@example.com": "U0001"}
