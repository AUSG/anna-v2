import logging
import traceback
from functools import wraps

from config.env_config import envs
from util.utils import search_value, strip_multiline

ADMIN_CHANNEL = envs.ADMIN_CHANNEL


def catch_global_error():
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger(f.__name__)
            event, say, respond = (
                kwargs.get("event", None) or kwargs.get("body", None),
                kwargs.get("say", None),
                kwargs.get("respond", None),
            )

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
                say(
                    text=err_msg, channel=ADMIN_CHANNEL
                )  # send full log to admin channel

                # notify user that something is wrong.
                msg = ":blob-fearful: 요청이 정상적으로 처리되지 않았어. 운영진에게 알려줘!"
                if respond:
                    respond(msg)
                else:
                    say(
                        text=msg,
                        channel=search_value(event, "channel_id")
                        or search_value(event, "channel_id")
                        or ADMIN_CHANNEL,
                    )

        return wrapper

    return decorator
