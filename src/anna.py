from datetime import datetime
import logging
import os
from slack_bolt import App

from configuration import init_log, init_env
from apscheduler.schedulers.background import BackgroundScheduler

init_log()
init_env()

from router import listen_event_with_services
from service import reply_to_question, participate_offline_meeting, track_thread, background_tracking_job

logger = logging.getLogger(__name__)


def enable_background_jobs():
    sched = BackgroundScheduler()
    for job in _JOBS:
        logger.info("새 job 등록: " + str(job.__name__))
        sched.add_job(job, 'cron', hour='0', id=str(job.__name__), next_run_time=datetime.now())
    sched.start()


SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')

_SERVICES = [reply_to_question, participate_offline_meeting, track_thread]
_JOBS = [background_tracking_job]

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

listen_event_with_services(app, _SERVICES)
enable_background_jobs()

if __name__ == '__main__':
    app.start(8080)
