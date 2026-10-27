"""도움말, 셔플과 빈 멘션 안내."""

import random
from typing import List

from features.bot_commands.models import Shuffle
from features.bot_commands.presentation.messages import (
    HELP_MESSAGE,
    UNKNOWN_COMMAND_MESSAGE,
    shuffled_message,
)
from shared.gateways import SlackGateway
from shared.slack_events import MentionEvent


def show_help(event: MentionEvent, slack: SlackGateway) -> bool:
    slack.send_thread_message(event.channel, event.ts, HELP_MESSAGE)
    return True


def shuffle_users(command: Shuffle, event: MentionEvent, slack: SlackGateway) -> bool:
    users: List[str] = list(command.user_ids)
    random.shuffle(users)
    slack.send_thread_message(event.channel, event.ts, shuffled_message(users))
    return True


def unknown_command(event: MentionEvent, slack: SlackGateway) -> bool:
    slack.send_thread_message(event.channel, event.ts, UNKNOWN_COMMAND_MESSAGE)
    return True
