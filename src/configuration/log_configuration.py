import logging

logger = logging.getLogger(__name__)

def init_log():
    logging.basicConfig(level=logging.DEBUG)

    logger.info("log configuration initialized")
