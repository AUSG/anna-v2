"""앱과 스케줄러를 초기화하고 Gunicorn에 flask_app을 제공한다."""

import logging

from app import create_app, start_schedulers
from config.log_config import init_logger

init_logger()
flask_app = create_app()
app = flask_app.extensions["slack_app"]
start_schedulers()

if __name__ == "__main__":
    PORT = 8080
    logging.getLogger(__name__).info("Anna wakes up at room %d", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)
