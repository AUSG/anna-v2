"""Slack API 응답을 옮겨 담는 값. SDK에 의존하지 않는다."""

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Message:
    ts: str
    thread_ts: str
    channel: str
    user: str
    text: str


@dataclass(frozen=True)
class Reaction:
    name: str
    users: List[str] = field(default_factory=list)
    count: int = 0
