import inspect
import logging

from config.env_config import envs


def init_logger():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        style="%",
        level=envs.LOGLEVEL,
    )

    get_logger().info("log config initialized")


def get_logger(module_name=""):
    if module_name == "":
        frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])
        module_name = mod.__name__

    return logging.getLogger(module_name)
