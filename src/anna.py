from datetime import datetime
import logging
from slack_bolt import App

from configuration import init_log, Configs
from apscheduler.schedulers.background import BackgroundScheduler

init_log()

from router import listen_event_with_services
from service import reply_to_question, participate_offline_meeting

logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = Configs.SLACK_BOT_TOKEN
SLACK_SIGNING_SECRET = Configs.SLACK_SIGNING_SECRET

_SERVICES = [
    # reply_to_question,
    participate_offline_meeting,
]

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

listen_event_with_services(app, _SERVICES)

if __name__ == "__main__":
    app.start(8080)
