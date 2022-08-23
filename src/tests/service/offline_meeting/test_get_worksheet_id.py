from unittest.mock import patch

from tests.util import add_dummy_envs

add_dummy_envs()

from service.offline_meeting.offline_meeting_participation_service import get_worksheet_id


def test_false_when_worksheet_id_found_in_thread():
    with patch(
            "service.offline_meeting.offline_meeting_service.find_worksheet_id_in_thread") as mock_find_worksheet_id_in_thread:
        mock_find_worksheet_id_in_thread.return_value = "12345"

        is_new, worksheet_id = get_worksheet_id(None, None, "123.45", "C1234")

        assert is_new is False
        assert worksheet_id == "12345"


def test_true_when_worksheet_id_not_found_in_thread():
    with patch(
            "service.offline_meeting.offline_meeting_service.find_worksheet_id_in_thread") as mock_find_worksheet_id_in_thread, \
            patch("implementation.google_spreadsheet_client.GoogleSpreadsheetClient") as mock_GoogleSpreadsheetClient:
        mock_find_worksheet_id_in_thread.return_value = None
        mock_GoogleSpreadsheetClient.return_value.create_worksheet.return_value = "67890"
        mock_gs_client = mock_GoogleSpreadsheetClient()

        is_new, worksheet_id = get_worksheet_id(None, mock_gs_client, "123.45", "C1234")

        assert is_new is True
        assert worksheet_id == "67890"
        assert mock_gs_client.create_worksheet.call_count == 1

