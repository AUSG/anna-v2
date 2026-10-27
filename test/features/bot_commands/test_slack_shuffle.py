import re
import unittest

from features.bot_commands.models import Shuffle, is_shuffle
from features.bot_commands.slack import shuffle_users
from shared.slack_events import MentionEvent
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import create_sample_app_mention_event

MENTION = re.compile(r"<@([A-Za-z0-9]+)>")


class TestShuffleUsers(unittest.TestCase):
    def _run(self, text, user_ids):
        assert is_shuffle(text)
        event = MentionEvent.from_payload(create_sample_app_mention_event(text))
        slack = fake_slack()
        result = shuffle_users(Shuffle(tuple(user_ids)), event, slack)
        slack.send_thread_message.assert_called_once()
        channel, ts, message = slack.send_thread_message.call_args.args
        assert (channel, ts) == (event.channel, event.ts)
        return result, message

    def test_run_by_korean(self):
        result, message = self._run(
            "<@U01BN035Y6L> 섞어줘 <@Uabc> <@Udef>", ["Uabc", "Udef"]
        )

        assert result is True
        assert message in ["여기있어!\n<@Uabc> <@Udef>", "여기있어!\n<@Udef> <@Uabc>"]

    def test_run_by_english(self):
        result, message = self._run(
            "<@U01BN035Y6L> shuffle <@Uabc> <@Udef>", ["Uabc", "Udef"]
        )

        assert result is True
        assert message in ["여기있어!\n<@Uabc> <@Udef>", "여기있어!\n<@Udef> <@Uabc>"]

    def test_every_given_user_is_mentioned_exactly_once(self):
        user_ids = [f"U{i:03d}" for i in range(20)]
        text = "<@U01BN035Y6L> shuffle " + " ".join(f"<@{u}>" for u in user_ids)

        result, message = self._run(text, user_ids)

        assert result is True
        header, _, body = message.partition("\n")
        assert header == "여기있어!"
        mentioned = MENTION.findall(body)
        assert sorted(mentioned) == sorted(user_ids)
        assert len(mentioned) == len(set(mentioned))
        assert body == " ".join(f"<@{u}>" for u in mentioned)
