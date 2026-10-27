"""실제 처리를 시작하는 지점에서만 loading 이모지를 붙이고, 끝나면 뗀다.

이모지 추가/삭제는 부가 기능이라 실패해도 본 작업을 막지 않고 로그만 남긴다.
붙이지 못했으면 떼려고도 하지 않는다. 삭제 실패가 본 작업의 예외를 덮어쓰지 않는다.
"""

import logging
from typing import Callable, TypeVar

from shared.gateways import SlackGateway

logger = logging.getLogger(__name__)
EMOJI_NAME = "loading"
T = TypeVar("T")


def with_loading_emoji(
    slack: SlackGateway, channel: str, ts: str, action: Callable[[], T]
) -> T:
    added = False
    if channel and ts:
        try:
            slack.add_reaction(channel, ts, EMOJI_NAME)
            added = True
        except Exception as ex:
            logger.warning("Failed to add loading emoji: %s", ex)
    try:
        return action()
    finally:
        if added:
            try:
                slack.remove_reaction(channel, ts, EMOJI_NAME)
            except Exception as ex:
                logger.warning("Failed to remove loading emoji: %s", ex)
