"""정기 빅챗 리마인더 진입점과 스케줄 등록."""

import logging
from functools import partial

from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from features.bigchat.services.reminders import RemindBigchat
from runtime import Runtime
from shared.scheduling import DailyScheduler, run_with_admin_alert
from shared.time import KST

logger = logging.getLogger(__name__)


def remind_bigchat(runtime: Runtime):
    logger.info("Bigchat reminder job invoked by scheduler")
    web_client = runtime.web_client()
    # 여러 명에게 연속으로 DM 을 보내다 429 를 맞으면 Retry-After 만큼 기다렸다 재시도한다
    web_client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=2))
    slack = runtime.slack_client(web_client)

    def job():
        result = RemindBigchat(slack, runtime.sheets(), runtime.members()).run()
        logger.info("Bigchat reminder job done: %d DM(s) sent", result.sent_cnt)

    run_with_admin_alert(
        job,
        label="빅챗 리마인더 DM 발송",
        slack=slack,
        admin_channel=runtime.settings.ADMIN_CHANNEL,
    )


def start_scheduler(runtime: Runtime):
    if not runtime.settings.BIGCHAT_REMINDER_ENABLED:
        return
    # 빅챗 전날 저녁 6시(KST)에 신청자들에게 리마인더 DM 을 보낸다
    DailyScheduler(
        job=partial(remind_bigchat, runtime),
        hour=18,
        minute=0,
        tz=KST,
        name="bigchat-reminder",
    ).start()
    logger.info("Bigchat reminder scheduler started (daily 18:00 KST)")
