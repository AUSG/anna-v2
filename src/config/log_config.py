import logging

from config.env_config import envs


def init_logger():
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        style="%",
        level=envs.LOGLEVEL,
    )

    logging.getLogger(__name__).info("log config initialized")
