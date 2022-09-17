from unittest.mock import patch

from tests.util import enable_dummy_envs

enable_dummy_envs()

from implementation import Message
from service.offline_meeting.action_commander import ActionCommander, TargetEvent, RejectCondition, ActionCommand


def _create_event(type, reaction, subtype, ts, channel):
    return {
        'type': type,
        'reaction': reaction,
        'subtype': subtype,
        'item': {
            'ts': ts,
            'channel': channel
        }
    }


def test_return_participate_command():
    with patch("implementation.SlackClient") as mock_slack_client:
        mock_slack_client.get_replies.return_value = [Message('1234.567', 'C1234567890')]
        mock_slack_client.get_emojis.return_value = []

        event = _create_event('reaction_added', 'submit_form_emoji', None, '1234.567', 'C1234567890')
        sut = ActionCommander(event, mock_slack_client)

        command = sut.decide(TargetEvent('submit_form_emoji', 'C1234567890'), RejectCondition('reject_emoji', 'reject_form_emoji'))

        assert command == ActionCommand.PARTICIPATE
        assert mock_slack_client.get_replies.call_count == 1
        assert mock_slack_client.get_emojis.call_count == 1
