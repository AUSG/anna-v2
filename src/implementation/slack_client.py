import logging
from typing import List, Optional

import requests
from pydantic import BaseModel
from slack_bolt import Say
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

logger = logging.getLogger(__name__)


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

    def send_thread_message(self, msg: str, channel: str, ts: str):
        """say 컨텍스트가 없는 경우(모달 제출 등)에 채널/스레드를 직접 지정해서 메시지를 보낸다."""
        self.web_client.chat_postMessage(channel=channel, text=msg, thread_ts=ts)

    def send_response_url_message(self, response_url: str, msg: str):
        """상호작용 payload의 response_url로 응답한다. 봇이 채널 멤버가 아니어도 전달된다."""
        resp = requests.post(
            response_url,
            json={"response_type": "ephemeral", "text": msg},
            timeout=10,
        )
        resp.raise_for_status()

    def download_file(self, url: str) -> Optional[bytes]:
        """Slack url_private 파일을 봇 토큰으로 다운로드 (이미지 등). 실패 시 None."""
        try:
            resp = requests.get(
                url,
                headers={"Authorization": f"Bearer {self.web_client.token}"},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to download Slack file: {e}")
            return None

    def send_message_to_freetalk(self, msg: str):
        self.say(msg, channel="CQJ8HQWUV")

    def get_permalink(self, channel: str, ts: str) -> Optional[str]:
        """메시지 permalink를 반환. 실패 시 None."""
        try:
            resp = self.web_client.chat_getPermalink(channel=channel, message_ts=ts)
            return resp["permalink"]
        except SlackApiError as ex:
            logger.warning(f"Failed to get permalink: {ex}")
            return None

    def send_message_only_visible_to_user(
        self,
        msg: str,
        user_id: str,
        channel: str,
        ts: Optional[str] = None,
        blocks: Optional[List[dict]] = None,
    ):
        self.web_client.chat_postEphemeral(
            text=msg, blocks=blocks, channel=channel, user=user_id, thread_ts=ts
        )

    @staticmethod
    def _messages_to_members(messages, channel):
        return [
            Message(
                ts=msg["ts"],
                thread_ts=msg.get("thread_ts") or msg.get("ts"),
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
        XXX: 대댓글이 하나도 없을 경우 thread_ts 값이 비어있을 수 있음
        """
        # [FIXME] default 값이 해당 쓰레드의 메시지 1000 개를 가져오는 것인데,
        #     혹시라도 쓰레드의 댓글이 첫 글 포함 1000개가 넘을경우 먼저 작성된 1000개를 가져올지,
        #     아니면 나중에 작성된 1000개를 가져올지에 대해 체크해보지 않음.
        #     만약 후자일 경우 이 코드가 쓰레드의 제일 첫번째 메시지를 가져올 수 있도록 수정해야 함.

        if ts:
            msg = self.get_replies(thread_ts=ts, channel=channel)[0]
            thread_ts = msg.thread_ts

        for attempt in range(3):
            try:
                resp = self.web_client.conversations_replies(
                    ts=thread_ts, channel=channel
                )
                break
            except OSError:
                if attempt >= 2:
                    raise

        if resp.status_code != 200:
            raise Exception(f"Failed to get message, ts={thread_ts}, channel={channel}")

        return self._messages_to_members(resp["messages"], channel)

    def add_emoji(self, channel, ts, emoji_name):
        try:
            self.web_client.reactions_add(
                channel=channel, name=emoji_name, timestamp=ts
            )
        except SlackApiError as ex:
            if ex.response.data["error"] == "already_reacted":
                return
            raise ex

    def remove_emoji(self, channel, ts, emoji_name):
        try:
            self.web_client.reactions_remove(
                channel=channel, name=emoji_name, timestamp=ts
            )
        except SlackApiError as ex:
            if ex.response.data["error"] == "no_reaction":
                return
            raise ex
