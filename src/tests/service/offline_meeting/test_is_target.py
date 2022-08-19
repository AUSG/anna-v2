import os
from unittest.mock import patch

from tests.util import add_dummy_envs

add_dummy_envs()

from service.offline_meeting.offline_meeting_service import is_target


def _create_event():
    event = {'type': 'emoji_changed',
             'reaction': os.environ.get('SUBMIT_FORM_EMOJI'),
             'subtype': 'add',
             'user': 'U12345',
             'item': {'ts': '123.45', 'channel': os.environ.get('ANNOUNCEMENT_CHANNEL_ID')}}
    return event


def test_false_when_type_not_exist():
    event = _create_event()
    del event['type']
    assert is_target(event, None) is False

def test_false_when_reaction_not_exist():
    event = _create_event()
    del event['reaction']
    assert is_target(event, None) is False

def test_false_when_subtype_not_exist():
    event = _create_event()
    del event['subtype']
    assert is_target(event, None) is False

def test_false_when_user_not_exist():
    event = _create_event()
    del event['user']
    assert is_target(event, None) is False

def test_false_when_ts_not_exist():
    event = _create_event()
    del event['item']['ts']
    assert is_target(event, None) is False

def test_false_when_channel_not_exist():
    event = _create_event()
    del event['item']['channel']
    assert is_target(event, None) is False


def test_false_when_channel_not_announcement_channel():
    event = _create_event()
    event['item']['channel'] = 'C12345'
    assert is_target(event, None) is False

def test_false_when_event_is_in_reply_in_thread():
    with patch('service.offline_meeting.offline_meeting_service.is_reply_in_thread') as mock_is_reply_in_thread:
        mock_is_reply_in_thread.return_value = True
        event = _create_event()
        assert is_target(event, None) is False


def test_true_when_event_is_in_reply_in_thread():
    with patch('service.offline_meeting.offline_meeting_service.is_reply_in_thread') as mock_is_reply_in_thread:
        mock_is_reply_in_thread.return_value = False
        event = _create_event()
        assert is_target(event, None) is True
