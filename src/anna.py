import os
from slack_bolt import App

from configuration import init_log, init_env

init_log()
init_env("../")


from router import listen_event_with_services
from service import reply_to_question, register_meeting

SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')

_SERVICES = [reply_to_question, register_meeting]

app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)

listen_event_with_services(app, _SERVICES)


if __name__ == '__main__':
    app.start(8080)
