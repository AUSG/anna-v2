from unittest.mock import patch

from tests.util import enable_dummy_envs

enable_dummy_envs()

from service.offline_meeting.offline_meeting_participation_service import is_reply_in_thread


def test_false_when_no_reply():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.return_value.conversations_replies.return_value = {'messages': [{}]}

        assert is_reply_in_thread(mock_web_client(), None, None) is False


def test_false_when_thread_ts_and_ts_are_same():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.return_value.conversations_replies.return_value = {
            'messages': [{'thread_ts': "12345", 'ts': "12345"}]}

        assert is_reply_in_thread(mock_web_client(), None, None) is False


def test_true_when_thread_ts_and_ts_are_different():
    with patch('slack_sdk.web.WebClient') as mock_web_client:
        mock_web_client.return_value.conversations_replies.return_value = {
            'messages': [{'thread_ts': "12345", 'ts': "67890"}]}

        assert is_reply_in_thread(mock_web_client(), None, None) is True
