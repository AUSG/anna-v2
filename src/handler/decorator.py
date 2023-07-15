import logging
import traceback
from functools import wraps

from config.env_config import envs
from implementation.slack_client import SlackClient
from util.utils import search_value, strip_multiline

ADMIN_CHANNEL = envs.ADMIN_CHANNEL


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
                say(
                    text=err_msg, channel=ADMIN_CHANNEL
                )  # send full log to admin channel

                # notify user that something is wrong.
                msg = ":blob-fearful: 요청이 정상적으로 처리되지 않았어. 운영진에게 알려줘!"
                say(
                    text=msg,
                    channel=search_value(event, "channel")
                    or search_value(event, "channel_id")
                    or ADMIN_CHANNEL,
                    thread_ts=search_value(event, "ts")
                    or search_value(event, "thread_ts"),
                )

        return wrapper

    return decorator


def loading_emoji_while_processing():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            slack_client = SlackClient(kwargs["say"], kwargs["client"])
            channel = search_value(kwargs["event"], "channel")
            ts = search_value(kwargs["event"], "ts")

            ex = None

            try:
                slack_client.add_emoji(channel, ts, "loading")
            except Exception:
                pass

            try:
                f(*args, **kwargs)
            except Exception as ex2:
                ex = ex2
                pass

            try:
                slack_client.remove_emoji(channel, ts, "loading")
            except Exception:
                pass

            if ex:
                raise ex

        return wrapper

    return decorator
