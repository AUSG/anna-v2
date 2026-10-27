"""데일리 핫스레드 게시 진입점과 스케줄 등록."""

import logging
from functools import partial

from runtime import Runtime
from shared.scheduling import DailyScheduler, run_with_admin_alert
from shared.time import KST

logger = logging.getLogger(__name__)


def post_daily_digest(runtime: Runtime):
    slack = runtime.slack_client(runtime.web_client())

    def job():
        text = runtime.qa().daily_digest()
        if not text:
            logger.info("Daily digest: nothing to post")
            return
        slack.send_markdown(runtime.settings.DAILY_DIGEST_CHANNEL_ID, text)
        logger.info("Daily digest posted")

    run_with_admin_alert(
        job,
        label="데일리 핫스레드 게시",
        slack=slack,
        admin_channel=runtime.settings.ADMIN_CHANNEL,
    )


def start_scheduler(runtime: Runtime):
    if not runtime.settings.DAILY_DIGEST_ENABLED:
        return
    # 어제의 핫스레드를 매일 아침 10시(KST)에 fun-anna-house 에 올린다
    DailyScheduler(
        job=partial(post_daily_digest, runtime),
        hour=10,
        minute=0,
        tz=KST,
        name="daily-digest",
    ).start()
    logger.info("Daily digest scheduler started (daily 10:00 KST)")
