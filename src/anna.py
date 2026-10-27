"""앱과 스케줄러를 초기화하고 Gunicorn에 flask_app을 제공한다."""

import logging

from app import create_app, start_schedulers
from bootstrap import create_runtime
from config.log_config import init_logger

runtime = create_runtime()
init_logger(runtime.settings.LOGLEVEL)
flask_app = create_app(runtime)
app = flask_app.extensions["slack_app"]
start_schedulers(runtime)

if __name__ == "__main__":
    PORT = 8080
    logging.getLogger(__name__).info("Anna wakes up at room %d", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)
