import logging

from configuration.env_configuration import is_local

logger = logging.getLogger(__name__)

def init_log():
    if is_local():
        logging.basicConfig(level=logging.INFO)
    else:
        logging.basicConfig(level=logging.INFO)

    logger.info("log configuration initialized")
