"""Slack 진입점에서 공유하는 오류 알림과 로딩 표시."""

import logging
import traceback
from functools import wraps

from config.env_config import envs
from integrations.slack import NO_UNFURL
from shared.mappings import search_value
from shared.text import strip_multiline

ADMIN_CHANNEL = envs.ADMIN_CHANNEL
EMOJI_NAME = "loading"


def catch_global_error():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(f.__name__)
            event = kwargs["event"]
            try:
                logger.debug("event=%s", event)
                f(*args, **kwargs)
            except BaseException as ex:
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
                    str(ex),
                    str(traceback.format_exc()),
                )
                logger.error(err_msg)
                logger.error(event)
                say = kwargs["say"]
                say(text=err_msg, channel=ADMIN_CHANNEL, **NO_UNFURL)
                say(
                    text=(
                        ":blob-fearful: 요청이 정상적으로 처리되지 않았어. "
                        "한 번 더 시도해보고, 그래도 안되면 운영진에게 알려줘!"
                    ),
                    channel=search_value(event, "channel")
                    or search_value(event, "channel_id")
                    or ADMIN_CHANNEL,
                    thread_ts=search_value(event, "ts")
                    or search_value(event, "thread_ts"),
                    **NO_UNFURL,
                )

        return wrapper

    return decorator


class LoadingEmoji:
    """부가 이모지 작업의 실패가 본 작업이나 원래 오류를 덮어쓰지 않게 한다."""

    def __init__(self, slack_client, channel, ts):
        self.slack_client = slack_client
        self.channel = channel
        self.ts = ts
        self._added = False

    def __enter__(self):
        if not self.channel or not self.ts:
            return self
        try:
            self.slack_client.add_emoji(self.channel, self.ts, EMOJI_NAME)
            self._added = True
        except Exception as ex:
            logging.getLogger(__name__).warning("Failed to add loading emoji: %s", ex)
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._added:
            return False
        self._added = False
        try:
            self.slack_client.remove_emoji(self.channel, self.ts, EMOJI_NAME)
        except Exception as ex:
            logging.getLogger(__name__).warning(
                "Failed to remove loading emoji: %s", ex
            )
        return False
