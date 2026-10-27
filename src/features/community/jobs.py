"""데일리 핫스레드 게시 진입점과 스케줄 등록."""

import logging
import traceback
from functools import partial

from integrations.slack import NO_UNFURL
from shared.scheduling import DailyScheduler
from shared.time import KST

logger = logging.getLogger(__name__)


def post_daily_digest(dependencies):
    web_client = dependencies.create_web_client()
    try:
        text = dependencies._get_qa_client().daily_digest()
        if not text:
            logger.info("Daily digest: nothing to post")
            return
        dependencies.SlackClient(None, web_client).post_markdown(
            dependencies.envs.DAILY_DIGEST_CHANNEL_ID, text
        )
        logger.info("Daily digest posted")
    except Exception:
        logger.exception("Failed to post daily digest")
        try:
            web_client.chat_postMessage(
                channel=dependencies.envs.ADMIN_CHANNEL,
                text=f":blob-fearful: 데일리 핫스레드 게시 중 에러가 발생했어!\n```\n{traceback.format_exc()}\n```",
                **NO_UNFURL,
            )
        except Exception:
            logger.exception("Failed to notify admin channel")


def start_scheduler(dependencies):
    if not dependencies.envs.DAILY_DIGEST_ENABLED:
        return
    DailyScheduler(
        job=partial(post_daily_digest, dependencies),
        hour=10,
        minute=0,
        tz=KST,
        name="daily-digest",
    ).start()
    logger.info("Daily digest scheduler started (daily 10:00 KST)")
