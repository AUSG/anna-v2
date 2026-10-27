import unittest

from features.bot_commands.models import is_help
from features.bot_commands.presentation.messages import HELP_MESSAGE
from features.bot_commands.slack import show_help
from shared.slack_events import MentionEvent
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import create_sample_app_mention_event


class TestShowHelp(unittest.TestCase):
    def _run(self, text):
        event = MentionEvent.from_payload(create_sample_app_mention_event(text))
        slack = fake_slack()
        assert is_help(text)
        result = show_help(event, slack)
        return result, slack, event

    def test_run(self):
        result, slack, event = self._run("<@U01BN035Y6L> 도움!")

        assert result is True
        slack.send_thread_message.assert_called_once_with(
            event.channel, event.ts, HELP_MESSAGE
        )
        assert HELP_MESSAGE.startswith("나를 멘션했을 때, 사용할 수 있는 명령어야")

    def test_run_by_english(self):
        result, slack, event = self._run("<@U01BN035Y6L> help!")

        assert result is True
        slack.send_thread_message.assert_called_once_with(
            event.channel, event.ts, HELP_MESSAGE
        )
        assert slack.send_thread_message.call_args.args[2].startswith(
            "나를 멘션했을 때, 사용할 수 있는 명령어야"
        )
