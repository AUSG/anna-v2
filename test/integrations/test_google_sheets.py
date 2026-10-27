import unittest
from unittest.mock import MagicMock

from gspread.exceptions import WorksheetNotFound

from integrations.google_sheets import GoogleSpreadsheetClient
from shared.gateways import AppendOutcome

WORKSHEET_ID = 161837744


def create_sut():
    # 생성자는 실제 GCP 자격증명을 요구하므로 건너뛰고, 네트워크를 타는
    # _values/append_row 만 mock 으로 바꿔 append_row_if_absent 로직을 검증한다.
    sut = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    sut.spreadsheet_id = "SPREADSHEET"
    sut._values = MagicMock()
    sut.append_row = MagicMock()
    return sut


class TestAppendRowIfAbsent(unittest.TestCase):
    def test_appends_when_row_is_absent(self):
        sut = create_sut()
        sut._values.return_value = [[], ["a", "b", "c", "d"]]

        outcome = sut.append_row_if_absent(WORKSHEET_ID, ["x", "y", "z", "w"])

        assert outcome is AppendOutcome.ADDED
        sut.append_row.assert_called_once_with(WORKSHEET_ID, ["x", "y", "z", "w"])

    def test_skips_when_row_already_exists(self):
        sut = create_sut()
        sut._values.return_value = [[], ["x", "y", "z", "w"]]

        outcome = sut.append_row_if_absent(WORKSHEET_ID, ["x", "y", "z", "w"])

        assert outcome is AppendOutcome.ALREADY_PRESENT
        sut.append_row.assert_not_called()

    def test_compares_as_a_list_even_when_values_is_a_tuple(self):
        sut = create_sut()
        sut._values.return_value = [["x", "y"]]

        assert (
            sut.append_row_if_absent(WORKSHEET_ID, ("x", "y"))
            is AppendOutcome.ALREADY_PRESENT
        )

    def test_reports_missing_worksheet_when_reading(self):
        sut = create_sut()
        sut._values.side_effect = WorksheetNotFound()

        outcome = sut.append_row_if_absent(WORKSHEET_ID, ["x", "y", "z", "w"])

        assert outcome is AppendOutcome.WORKSHEET_MISSING
        sut.append_row.assert_not_called()

    def test_reports_missing_worksheet_when_appending(self):
        sut = create_sut()
        sut._values.return_value = []
        sut.append_row.side_effect = WorksheetNotFound()

        outcome = sut.append_row_if_absent(WORKSHEET_ID, ["x", "y", "z", "w"])

        assert outcome is AppendOutcome.WORKSHEET_MISSING


class TestMissingWorksheetBecomesValue(unittest.TestCase):
    """워크시트가 없는 경우는 예외가 아니라 값으로 돌려준다."""

    def test_get_values_returns_empty_list(self):
        sut = create_sut()
        sut._values.side_effect = WorksheetNotFound()

        assert sut.get_values(WORKSHEET_ID) == []

    def test_get_values_passes_cell_range(self):
        sut = create_sut()
        sut._values.return_value = [["a"]]

        assert sut.get_values(WORKSHEET_ID, "A1:A1") == [["a"]]
        sut._values.assert_called_once_with(WORKSHEET_ID, "A1:A1")

    def test_get_worksheet_title(self):
        sut = create_sut()
        sut._get_worksheet = MagicMock(return_value=MagicMock(title="AI 밋업"))

        assert sut.get_worksheet_title(WORKSHEET_ID) == "AI 밋업"

    def test_get_worksheet_title_returns_none_when_missing(self):
        sut = create_sut()
        sut._get_worksheet = MagicMock(side_effect=WorksheetNotFound())

        assert sut.get_worksheet_title(WORKSHEET_ID) is None


class TestDeleteRow(unittest.TestCase):
    def test_deletes_the_row_of_the_first_matching_cell(self):
        sut = create_sut()
        worksheet = MagicMock()
        worksheet.find.return_value = MagicMock(row=3)
        sut._get_worksheet = MagicMock(return_value=worksheet)

        assert sut.delete_row(WORKSHEET_ID, "U0001") is True

        worksheet.find.assert_called_once_with("U0001")
        worksheet.delete_rows.assert_called_once_with(3)

    def test_does_nothing_when_no_cell_matches(self):
        sut = create_sut()
        worksheet = MagicMock()
        worksheet.find.return_value = None
        sut._get_worksheet = MagicMock(return_value=worksheet)

        assert sut.delete_row(WORKSHEET_ID, "U0001") is True

        worksheet.delete_rows.assert_not_called()

    def test_returns_false_when_worksheet_is_missing(self):
        sut = create_sut()
        sut._get_worksheet = MagicMock(side_effect=WorksheetNotFound())

        assert sut.delete_row(WORKSHEET_ID, "U0001") is False


class TestGetUrl(unittest.TestCase):
    def test_points_at_the_worksheet_gid(self):
        sut = create_sut()

        assert (
            sut.get_url(WORKSHEET_ID)
            == "https://docs.google.com/spreadsheets/d/SPREADSHEET/edit#gid=161837744"
        )
