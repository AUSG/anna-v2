import unittest

from features.bot_commands.presentation.messages import UNKNOWN_COMMAND_MESSAGE
from features.bot_commands.slack import unknown_command
from shared.slack_events import MentionEvent
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import create_sample_app_mention_event


class TestUnknownCommand(unittest.TestCase):
    def _run(self, text):
        event = MentionEvent.from_payload(create_sample_app_mention_event(text))
        slack = fake_slack()
        return unknown_command(event, slack), slack, event

    def test_run(self):
        result, slack, event = self._run("<@U01BN035Y6L>")

        assert result is True
        slack.send_thread_message.assert_called_once_with(
            event.channel, event.ts, UNKNOWN_COMMAND_MESSAGE
        )
        assert UNKNOWN_COMMAND_MESSAGE == "앗, 잘못입력한 것 같아.\n나를 멘션하면서 help를 한 번 입력해봐!"

    def test_run_by_text_not_empty(self):
        result, slack, event = self._run("<@U01BN035Y6L> 안녕?")

        assert result is True
        slack.send_thread_message.assert_called_once_with(
            event.channel, event.ts, UNKNOWN_COMMAND_MESSAGE
        )
        assert (
            slack.send_thread_message.call_args.args[2]
            == "앗, 잘못입력한 것 같아.\n나를 멘션하면서 help를 한 번 입력해봐!"
        )
