import logging


def init_logger(level: str = "DEBUG"):
    logging.basicConfig(
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        style="%",
        level=level,
    )

    logging.getLogger(__name__).info("log config initialized")
