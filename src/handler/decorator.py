import traceback

from config.env_config import envs
from config.log_config import get_logger

ADMIN_CHANNEL = envs.ADMIN_CHANNEL


def catch_global_error(fn):
    def wrapped_fn(event, say, slack_client):
        logger = get_logger(fn.__name__)
        try:
            logger.debug("event=%s", event)
            fn(event, say, slack_client)
        except BaseException as ex:
            err_msg = f"""예상치 못한 에러가 발생했어!
- event={event}
- exception={ex}
- traceback={traceback.format_exc()})
"""
            logger.error(err_msg)
            say(text=err_msg, channel=ADMIN_CHANNEL)
            say(
                text="이 메시지가 보인다면 ANNA에 뭔가 문제가 생겼단 뜻이야. 운영진에게 알려줘!",
                channel=event["item"]["channel"],
                user=event["user"],
                thread_ts=event["item"]["ts"],
            )

    return wrapped_fn
