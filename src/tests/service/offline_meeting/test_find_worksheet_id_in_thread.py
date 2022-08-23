import os
from unittest.mock import patch

from tests.util import add_dummy_envs

add_dummy_envs()

from service.offline_meeting.offline_meeting_participation_service import find_worksheet_id_in_thread

def test_none_with_empty_response():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.mock_conversations_replies.return_value = {'messages': [{'user': "asd", 'text': 'hello'}]}

        assert find_worksheet_id_in_thread(mock_web_client, None, None) is None


def test_none_when_spreadsheet_url_pattern_not_in_messages():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.mock_conversations_replies.return_value = {'messages': [{'user': "me", 'text': 'hello'}]}

        assert find_worksheet_id_in_thread(mock_web_client, None, None) is None


def test_none_when_spreadsheet_url_pattern_in_messages_not_by_anna():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.mock_conversations_replies.return_value = {'messages': [{'user': "me", 'text': 'https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=1234'}]}

        assert find_worksheet_id_in_thread(mock_web_client, None, None) is None

def test_none_when_spreadsheet_url_pattern_not_in_messages_by_anna():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.conversations_replies.return_value = {'messages': [{'user': os.environ.get('ANNA_ID'), 'text': 'https://docs.google.com'}]}

        assert find_worksheet_id_in_thread(mock_web_client, None, None) is None

def test_success_when_spreadsheet_url_pattern_in_messages_by_anna():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.conversations_replies.return_value = {'messages': [{'user': os.environ.get('ANNA_ID'), 'text': 'https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=1234'}]}

        assert find_worksheet_id_in_thread(mock_web_client, None, None) == 1234
