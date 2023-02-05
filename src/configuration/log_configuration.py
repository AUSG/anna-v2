import logging

from configuration import Configs

logger = logging.getLogger(__name__)

def init_log():
    if Configs.LOCAL:
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info("log configuration initialized")
