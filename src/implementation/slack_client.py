from typing import List, Optional

from pydantic import BaseModel
from slack_bolt import Say
from slack_sdk import WebClient


class Message(BaseModel):
    ts: str
    thread_ts: str
    channel: str
    user: str
    text: str


class Emoji(BaseModel):
    user: str
    name: str


class SlackClient:
    def __init__(self, say: Say, web_client: WebClient):
        self.say = say
        self.web_client = web_client

    def send_message(self, msg: str, ts: str):
        self.say(msg, thread_ts=ts)

    def send_message_only_visible_to_user(
        self, msg: str, user_id: str, channel: str, thread_ts: Optional[str] = None
    ):
        self.web_client.chat_postEphemeral(
            text=msg, channel=channel, user=user_id, thread_ts=thread_ts
        )

    @staticmethod
    def _messages_to_members(messages, channel):
        return [
            Message(
                ts=msg["ts"],
                thread_ts=msg["thread_ts"],
                channel=channel,
                user=msg["user"],
                text=msg["text"],
            )
            for msg in messages
        ]

    def get_replies(
        self, channel: str, thread_ts: str = None, ts: str = None
    ) -> List[Message]:
        """
        해당 스레드 첫 댓글의 ts, 즉 thread_ts 를 넣어야 정상적으로 목록을 가져옴 (대댓글 X)

        :param ts: thread_ts 를 모를 경우, ts 를 이용해 해당 message 로 구성된 1 length replies 를
          가져온 후, 그 message 에 포함된 thread_ts 를 이용해 다시 조회해온다.

        ref: https://api.slack.com/methods/conversations.replies#examples
        """
        # [FIXME] default 값이 해당 쓰레드의 메시지 1000 개를 가져오는 것인데,
        #     혹시라도 쓰레드의 댓글이 첫 글 포함 1000개가 넘을경우 먼저 작성된 1000개를 가져올지,
        #     아니면 나중에 작성된 1000개를 가져올지에 대해 체크해보지 않음.
        #     만약 후자일 경우 이 코드가 쓰레드의 제일 첫번째 메시지를 가져올 수 있도록 수정해야 함.

        if ts:
            msg = self.get_replies(thread_ts=ts, channel=channel)[0]
            thread_ts = msg.thread_ts

        resp = self.web_client.conversations_replies(ts=thread_ts, channel=channel)

        if resp.status_code != 200:
            raise Exception(f"Failed to get message, ts={thread_ts}, channel={channel}")

        return self._messages_to_members(resp["messages"], channel)
