"""진입점에서 잡은 예외를 관리자와 요청자에게 알린다."""

import logging
import traceback

from shared.gateways import SlackGateway
from shared.slack_events import reply_target
from shared.text import strip_multiline

logger = logging.getLogger(__name__)

USER_NOTICE = "".join(
    (
        ":blob-fearful: 요청이 정상적으로 처리되지 않았어. ",
        "한 번 더 시도해보고, 그래도 안되면 운영진에게 알려줘!",
    )
)


def report_failure(
    slack: SlackGateway, admin_channel: str, event: dict, exc: BaseException
) -> None:
    err_msg = strip_multiline(
        """
        :blob-fearful: 예상치 못한 에러가 발생했어!
        :point_right: event:
        ```
        {}
        ```
        
        :point_right: exception:
        ```
        {}
        ```
        :point_right: traceback:
        ```
        {}
        ```""",
        str(event),
        str(exc),
        "".join(traceback.format_exception(exc)),
    )
    logger.error(err_msg)
    logger.error(event)
    slack.send_channel_message(admin_channel, err_msg)
    channel, ts = reply_target(event)
    if channel and ts:
        slack.send_thread_message(channel, ts, USER_NOTICE)
    else:
        slack.send_channel_message(channel or admin_channel, USER_NOTICE)
