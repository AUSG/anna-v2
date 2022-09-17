import unittest
from unittest.mock import patch

from tests.util import add_dummy_envs

add_dummy_envs()

from service.offline_meeting import Member
from service.offline_meeting.offline_meeting_participation_service import main


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
            patch('slack_sdk.web.WebClient') as mock_web_client, \
            patch('slack_bolt.Say') as mock_say, \
            patch('service.offline_meeting.offline_meeting_participation_service.find_member') as mock_find_member:
        mock_web_client.conversations_replies.return_value = {'messages': [{'user': 'U1234567890'}]}
        mock_find_member.return_value = _dummy_member()
        mock_gs_client.create_worksheet.return_value = '123456789'
        mock_gs_client.append_row.return_value = None
        mock_say.return_value = None

        event = _dummy_event()
        main(event, mock_say, mock_web_client, mock_gs_client)

        mock_find_member.assert_called_once()
        mock_gs_client.create_worksheet.assert_called_once()
        mock_gs_client.append_row.assert_called_once()
        assert mock_web_client.conversations_replies.call_count == 2
        assert mock_say.call_count == 2
