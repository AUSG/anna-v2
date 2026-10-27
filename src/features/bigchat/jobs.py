"""정기 빅챗 리마인더 진입점과 스케줄 등록."""

import logging
import traceback
from functools import partial

from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from features.bigchat.services.reminders import RemindBigchat
from integrations.slack import NO_UNFURL
from shared.scheduling import DailyScheduler
from shared.time import KST

logger = logging.getLogger(__name__)


def remind_bigchat(dependencies):
    logger.info("Bigchat reminder job invoked by scheduler")
    web_client = dependencies.create_web_client()
    web_client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=2))
    try:
        result = RemindBigchat(
            dependencies.SlackClient(None, web_client),
            dependencies.GoogleSpreadsheetClient(),
            dependencies._get_member_manager(),
        ).run()
        logger.info("Bigchat reminder job done: %d DM(s) sent", result.sent_cnt)
    except Exception:
        logger.exception("Failed to send bigchat reminders")
        try:
            web_client.chat_postMessage(
                channel=dependencies.envs.ADMIN_CHANNEL,
                text=f":blob-fearful: 빅챗 리마인더 DM 발송 중 에러가 발생했어!\n```\n{traceback.format_exc()}\n```",
                **NO_UNFURL,
            )
        except Exception:
            logger.exception("Failed to notify admin channel")


def start_scheduler(dependencies):
    if not dependencies.envs.BIGCHAT_REMINDER_ENABLED:
        return
    DailyScheduler(
        job=partial(remind_bigchat, dependencies),
        hour=18,
        minute=0,
        tz=KST,
        name="bigchat-reminder",
    ).start()
    logger.info("Bigchat reminder scheduler started (daily 18:00 KST)")
