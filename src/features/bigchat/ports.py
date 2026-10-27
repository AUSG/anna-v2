"""빅챗 업무가 저장소에 요구하는 계약."""

from typing import Protocol

from features.bigchat.models import BigchatCreated


class BigchatRepository(Protocol):
    def create(self, sheet_name: str) -> BigchatCreated:
        ...
