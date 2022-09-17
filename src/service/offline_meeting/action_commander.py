from dataclasses import dataclass
from enum import Enum, auto

from implementation import SlackClient, Emoji, Message
from util import SlackGeneralEvent, get_prop


class ActionCommand(Enum):
    NOOP = auto()
    REJECT = auto()
    PARTICIPATE = auto()


@dataclass
class TargetEvent:
    emoji: str
    channel: str


@dataclass
class RejectCondition:
    emoji: str
    user: str


@dataclass
class Event:
    type: str
    reaction: str
    subtype: str
    ts: str
    channel: str


class ActionCommander:
    def __init__(self, event: SlackGeneralEvent, slack_client: SlackClient):
        self.slack_client = slack_client
        self.event = Event(
            type=get_prop(event, 'type'),
            reaction=get_prop(event, 'reaction'),
            subtype=get_prop(event, 'subtype'),
            ts=get_prop(event, 'item', 'ts'),
            channel=get_prop(event, 'item', 'channel'),
        )

    def decide(self, target_event: TargetEvent, reject_condition: RejectCondition) -> ActionCommand:
        if not self._is_target_event(target_event):
            return ActionCommand.NOOP
        elif self._is_reject_target(reject_condition):
            return ActionCommand.REJECT
        else:
            return ActionCommand.PARTICIPATE

    def _is_target_event(self, target_event: TargetEvent):
        return (self._is_newly_added_emoji() and
                self._is_target_emoji(target_event.emoji) and
                self._is_target_channel(target_event.channel) and
                self._is_first_message_on_thread())

    def _is_target_channel(self, target_channel):
        return self.event.channel == target_channel

    def _is_target_emoji(self, participate_emoji):
        return self.event.reaction == participate_emoji

    def _is_newly_added_emoji(self):
        return self.event.type == "reaction_added"

    def _is_first_message_on_thread(self):
        msg = Message(self.event.ts, self.event.channel)

        messages = self.slack_client.get_replies(ts=self.event.ts, channel=self.event.channel)
        first_message = messages[0]

        return msg == first_message

    def _is_reject_target(self, reject_condition: RejectCondition) -> bool:
        reject_emoji = Emoji(reject_condition.user, reject_condition.emoji)

        emojis = self.slack_client.get_emojis(self.event.channel, self.event.ts)

        return reject_emoji in emojis
