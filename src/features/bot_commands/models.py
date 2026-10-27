"""도움말, 셔플, 빈 멘션 명령."""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Shuffle:
    user_ids: Tuple[str, ...]


@dataclass(frozen=True)
class Help:
    pass


@dataclass(frozen=True)
class Empty:
    pass


def is_shuffle(text: str) -> bool:
    return "섞어줘" in text or "shuffle" in text.lower()


def is_help(text: str) -> bool:
    return "help" in text or "도움" in text
