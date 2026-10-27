"""Slack 페이로드를 진입점에서 한 번만 값으로 바꾼다.

이후 코드는 dict 를 들여다보지 않는다. 필드는 실제로 쓰는 것만 담는다.
"""

import json
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Tuple


def is_edited_message(event) -> bool:
    """이미 올라온 메시지를 고쳐서 온 이벤트인지.

    슬랙은 메시지 '수정'에도 이벤트를 보내는데, 새 글과 똑같이 처리하면
    같은 멘션 명령이 한 번 더 실행되고(리마인더 재발송 등) 답글도 중복으로 달린다.
    수정 사실은 이벤트 종류마다 다른 자리에 실려온다:

    - message: subtype 이 'message_changed' 이고, 본문은 event['message'] 아래로 내려간다
    - app_mention: 최상위에 'edited' 가 붙는다 (이미 있던 멘션을 고치면 다시 발생)
    """
    if not isinstance(event, dict):
        return False
    if event.get("subtype") == "message_changed":
        return True
    if event.get("edited"):
        return True
    if (event.get("message") or {}).get("edited"):
        return True
    return False


def reply_target(event: dict) -> Tuple[Optional[str], Optional[str]]:
    """오류 안내를 달 (channel, thread_ts). 이벤트 종류별로 자리가 다르다."""
    channel = event.get("channel")
    if isinstance(channel, dict):
        channel = channel.get("id")
    item = event.get("item") or {}
    channel = channel or item.get("channel") or event.get("channel_id")
    ts = event.get("ts") or item.get("ts") or event.get("thread_ts")
    return channel, ts


@dataclass(frozen=True)
class MentionEvent:
    text: str
    user: str
    channel: str
    ts: str
    thread_ts: Optional[str] = None

    @classmethod
    def from_payload(cls, event: dict) -> "MentionEvent":
        return cls(
            text=event["text"],
            user=event["user"],
            channel=event["channel"],
            ts=event["ts"],
            thread_ts=event.get("thread_ts"),
        )

    @property
    def root_ts(self) -> str:
        """스레드 안이면 첫 글, 아니면 이 글 자신."""
        return self.thread_ts or self.ts


@dataclass(frozen=True)
class ReactionEvent:
    kind: Literal["reaction_added", "reaction_removed"]
    user: str
    reaction: str
    channel: str
    ts: str

    @classmethod
    def from_payload(cls, event: dict) -> "ReactionEvent":
        return cls(
            kind=event["type"],
            user=event["user"],
            reaction=event["reaction"],
            channel=event["item"]["channel"],
            ts=event["item"]["ts"],
        )


@dataclass(frozen=True)
class SlackFile:
    mimetype: str
    url: str


@dataclass(frozen=True)
class MessageEvent:
    channel: str
    ts: str
    text: str = ""
    user: Optional[str] = None
    thread_ts: Optional[str] = None
    subtype: Optional[str] = None
    bot_id: Optional[str] = None
    files: List[SlackFile] = field(default_factory=list)

    @classmethod
    def from_payload(cls, event: dict) -> "MessageEvent":
        files = []
        for f in event.get("files") or []:
            url = f.get("url_private_download") or f.get("url_private") or ""
            files.append(SlackFile(mimetype=f.get("mimetype") or "", url=url))
        return cls(
            channel=event.get("channel") or "",
            ts=event.get("ts") or "",
            text=event.get("text") or "",
            user=event.get("user"),
            thread_ts=event.get("thread_ts"),
            subtype=event.get("subtype"),
            bot_id=event.get("bot_id"),
            files=files,
        )


@dataclass(frozen=True)
class ChannelCreatedEvent:
    channel_id: str

    @classmethod
    def from_payload(cls, event: dict) -> "ChannelCreatedEvent":
        return cls(channel_id=event["channel"]["id"])


@dataclass(frozen=True)
class ShortcutPayload:
    """메시지 단축메뉴. ts 는 실행한 메시지가 속한 스레드의 첫 글이다."""

    trigger_id: str
    channel: str
    thread_ts: str
    user: str
    response_url: str = ""

    @classmethod
    def from_payload(cls, body: dict) -> "ShortcutPayload":
        message = body.get("message", {})
        return cls(
            trigger_id=body["trigger_id"],
            channel=body["channel"]["id"],
            thread_ts=message.get("thread_ts") or message.get("ts"),
            user=body["user"]["id"],
            response_url=body.get("response_url", ""),
        )


@dataclass(frozen=True)
class ViewSubmission:
    """모달 제출. private_metadata 에 실어 보낸 실행 컨텍스트를 복원한다."""

    channel: str
    thread_ts: str
    user: str
    response_url: str
    values: dict

    @classmethod
    def from_payload(cls, body: dict) -> "ViewSubmission":
        metadata = json.loads(body["view"]["private_metadata"])
        return cls(
            channel=metadata["channel"],
            thread_ts=metadata["thread_ts"],
            user=body["user"]["id"],
            response_url=metadata.get("response_url", ""),
            values=body["view"]["state"]["values"],
        )
