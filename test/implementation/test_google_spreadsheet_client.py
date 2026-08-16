import unittest
from unittest.mock import MagicMock

from implementation.google_spreadsheet_client import GoogleSpreadsheetClient


def create_sut():
    # 생성자는 실제 GCP 자격증명을 요구하므로 건너뛰고, 네트워크를 타는
    # get_values/append_row 만 mock 으로 바꿔 append_row_if_absent 로직을 검증한다.
    sut = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    sut.get_values = MagicMock()
    sut.append_row = MagicMock()
    return sut


class TestAppendRowIfAbsent(unittest.TestCase):
    def test_appends_when_row_is_absent(self):
        sut = create_sut()
        sut.get_values.return_value = [[], ["a", "b", "c", "d"]]

        assert sut.append_row_if_absent(161837744, ["x", "y", "z", "w"]) is True

        sut.append_row.assert_called_once_with(161837744, ["x", "y", "z", "w"])

    def test_skips_when_row_already_exists(self):
        sut = create_sut()
        sut.get_values.return_value = [[], ["x", "y", "z", "w"]]

        assert sut.append_row_if_absent(161837744, ["x", "y", "z", "w"]) is False

        sut.append_row.assert_not_called()
