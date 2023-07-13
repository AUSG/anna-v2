from dataclasses import field
from typing import List, Optional

from pydantic import BaseModel
from slack_bolt import Say
from slack_sdk import WebClient


class Message(BaseModel):
    ts: str
    thread_ts: str
    channel: str
    user: str = field(compare=False, default="")
    text: str = field(compare=False, default="")


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

    def _messages_to_members(self, messages, channel):
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
        #     혹시라도 쓰레드의 댓글이 첫 글 포함 1000개가 넘을경우 먼저 작성된 1000개를 가져올지, 나중에 작성된 1000개를 가져올지에 대해 체크해보지 않음.
        #     만약 후자일 경우 이 코드가 쓰레드의 제일 첫번째 메시지를 가져올 수 있도록 수정해야 함

        if ts:
            msg = self.get_replies(thread_ts=ts, channel=channel)[0]
            thread_ts = msg.thread_ts

        resp = self.web_client.conversations_replies(ts=thread_ts, channel=channel)

        if resp.status_code != 200:
            raise Exception(f"Failed to get message, ts={thread_ts}, channel={channel}")

        return self._messages_to_members(resp["messages"], channel)

    def get_emojis(self, channel: str, ts: str) -> List[Emoji]:
        """
        res: https://api.slack.com/methods/reactions.get#examples
        """
        resp = self.web_client.reactions_get(channel=channel, timestamp=ts, full=True)

        emojis = []
        reactions = (
            resp["message"]["reactions"] if "reactions" in resp["message"] else []
        )
        for reaction in reactions:
            for user in reaction["users"]:
                emojis.append(Emoji(user=user, name=reaction["name"]))

        return emojis

    def open_view_for_create_bigchat_sheet(self, trigger_id):
        self.web_client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "CREATE_BIGCHAT_SHEET_FORM_SUBMIT",  # Used when calling view_closed
                "title": {"type": "plain_text", "text": "새로운 빅챗 시트를 만들 시간이야?"},
                "submit": {
                    "type": "plain_text",
                    "text": "생성",
                },
                "close": {
                    "type": "plain_text",
                    "text": "취소",
                },
                "notify_on_close": False,
                "blocks": [
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "plain_text",
                                "text": "(스레드 안에서 만드는 걸 추천해!)",
                                "emoji": True,
                            }
                        ],
                    },
                    {
                        "dispatch_action": False,
                        "type": "input",
                        "element": {
                            "type": "plain_text_input",
                            "action_id": "SHEET_NAME",
                        },
                        "label": {
                            "type": "plain_text",
                            "text": "시트 이름을 알려줘.",
                            "emoji": True,
                        },
                    },
                ],
            },
        )

    def open_view_for_notify_reqeust_fail(self, msg, trigger_id):
        self.web_client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "callback_id": "NOOP",
                "title": {"type": "plain_text", "text": "이런!"},
                "close": {
                    "type": "plain_text",
                    "text": "취소",
                },
                "notify_on_close": False,
                "blocks": [
                    {
                        "type": "context",
                        "elements": [
                            {"type": "plain_text", "text": msg, "emoji": True}
                        ],
                    }
                ],
            },
        )
