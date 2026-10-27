import logging

from config.env_config import envs


def init_logger(level=None):
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        style="%",
        level=envs.LOGLEVEL if level is None else level,
    )

    logging.getLogger(__name__).info("log config initialized")
