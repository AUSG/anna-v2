"""예약 작업의 실행 경계와 관리자 오류 알림. 의존성과 실행 시각은 anna.py가 조립한다."""

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass

from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from integrations.slack import NO_UNFURL, SlackClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    hour: int
    minute: int
    callback: Callable[[], None]


def remind_bigchat(*, web_client_factory, send_reminders, admin_channel: str):
    logger.info("Bigchat reminder job invoked by scheduler")
    web_client = web_client_factory()
    # 연속 DM의 429 응답은 Retry-After를 기다렸다 재시도한다.
    web_client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=2))
    try:
        result = send_reminders(SlackClient(None, web_client))
        logger.info("Bigchat reminder job done: %d DM(s) sent", result.sent_cnt)
    except Exception:
        logger.exception("Failed to send bigchat reminders")
        _notify_admin(
            web_client,
            admin_channel,
            ":blob-fearful: 빅챗 리마인더 DM 발송 중 에러가 발생했어!",
        )


def post_daily_digest(
    *, web_client_factory, fetch_digest, channel: str, admin_channel: str
):
    web_client = web_client_factory()
    try:
        text = fetch_digest()
        if not text:
            logger.info("Daily digest: nothing to post")
            return
        SlackClient(None, web_client).post_markdown(channel, text)
        logger.info("Daily digest posted")
    except Exception:
        logger.exception("Failed to post daily digest")
        _notify_admin(
            web_client,
            admin_channel,
            ":blob-fearful: 데일리 핫스레드 게시 중 에러가 발생했어!",
        )


def _notify_admin(web_client, channel: str, message: str):
    try:
        web_client.chat_postMessage(
            channel=channel,
            text=f"{message}\n```\n{traceback.format_exc()}\n```",
            **NO_UNFURL,
        )
    except Exception:
        logger.exception("Failed to notify admin channel")
