from dataclasses import dataclass, field
from typing import List, Optional

from slack_bolt import Say
from slack_sdk import WebClient


@dataclass
class Message:
    ts: str
    channel: str
    user: str = field(compare=False, default="")
    text: str = field(compare=False, default="")


@dataclass
class Emoji:
    user: str
    name: str


class SlackClient:
    def __init__(self, say: Say, web_client: WebClient):
        self.say = say
        self.web_client = web_client

    def tell(self, msg: str, ts: str):
        self.say(msg, thread_ts=ts)

    def send_message_only_visible_to_user(self, msg: str, user: str, channel: str, thread_ts: Optional[str] = None):
        self.web_client.chat_postEphemeral(text=msg, channel=channel, user=user, thread_ts=thread_ts)

    def get_replies(self, ts: str, channel: str) -> List[Message]:
        """
        ref: https://api.slack.com/methods/conversations.replies#examples
        """
        # [FIXME] default 값이 해당 쓰레드의 메시지 1000 개를 가져오는 것인데,
        #     혹시라도 쓰레드의 댓글이 첫 글 포함 1000개가 넘을경우 먼저 작성된 1000개를 가져올지, 나중에 작성된 1000개를 가져올지에 대해 체크해보지 않음.
        #     만약 후자일 경우 이 코드가 쓰레드의 제일 첫번째 메시지를 가져올 수 있도록 수정해야 함
        resp = self.web_client.conversations_replies(ts=ts, channel=channel)

        messages = [Message(msg['ts'], channel, msg['user'], msg['text']) for msg in resp["messages"]]
        return messages

    def get_emojis(self, channel: str, ts: str) -> List[Emoji]:
        """
        res: https://api.slack.com/methods/reactions.get#examples
        """
        resp = self.web_client.reactions_get(
            channel=channel,
            timestamp=ts,
            full=True
        )

        emojis = []
        reactions = resp["message"]["reactions"] if "reactions" in resp["message"] is not None else []
        for reaction in reactions:
            for user in reaction["users"]:
                emojis.append(Emoji(user, reaction["name"]))

        return emojis
