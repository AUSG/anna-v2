import threading
from unittest.mock import patch, Mock

from service.offline_meeting.action_commander import ActionCommand
from service.offline_meeting.member import Member
from service.offline_meeting.offline_meeting_participation_service import OfflineMeetingParticipationService


def _dummy_event():
    return {'type': 'reaction_added',
            'reaction': 'submit_form_emoji',
            'user': 'U1234567890',
            'item': {
                'ts': '1663216298.924399',
                'channel': 'announcement_channel_id'
            }}


def _dummy_member():
    return Member("문성혁", "Moon SeongHyeok", "roeniss2@gmail.com", "010-9003-4431", "토스페이먼츠")


def test_success():
    with patch("implementation.google_spreadsheet_client.GoogleSpreadsheetClient") as mock_gs_client, \
            patch('implementation.slack_client.SlackClient') as mock_slack_client, \
            patch('service.offline_meeting.action_commander.ActionCommander') as mock_action_commander:
        mock_slack_client.say.return_value = None
        mock_gs_client.append_row.return_value = None
        mock_action_commander.decide.return_value = ActionCommand.PARTICIPATE
        mock_member_finder = Mock()
        mock_member_finder.find.return_value = _dummy_member()
        mock_worksheet_maker = Mock()
        mock_worksheet_maker.find_or_create_worksheet.return_value = True, 12345

        event = _dummy_event()
        participate_single_lock: threading.Lock = threading.Lock()

        sut = OfflineMeetingParticipationService(event, mock_action_commander, mock_slack_client, mock_gs_client,
                                                 mock_member_finder, mock_worksheet_maker,
                                                 participate_single_lock=participate_single_lock)
        sut.run()

        mock_action_commander.decide.assert_called_once()
        mock_gs_client.append_row.assert_called_once()
        mock_worksheet_maker.find_or_create_worksheet.assert_called_once()
        assert mock_slack_client.tell.call_count == 2
        mock_member_finder.find.assert_called_once()
