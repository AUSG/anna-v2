import logging

from slack_sdk import WebClient
from slack_bolt import Say

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class SlackClient:
    def __init__(self, client: WebClient, say: Say):
        self.client = client
        self.say = say

    def send_msg(self, msg, ts=None, channel=None):
        if ts is not None:
            self.say(text=msg, thread_ts=ts)
        elif channel is not None:
            self.client.chat_postMessage(text=msg, channel=channel)

    def get_replies(self, ts: str, channel: str):
        self.client.conversations_replies(ts=ts, channel=channel)
