import logging
import os

import env_bucket
from offiline_meeting.controller import OmHandler
from slack_bolt import App


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = env_bucket.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = env_bucket.get('SLACK_SIGNING_SECRET')

app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET
)

event_handlers = [OmHandler()]


@app.event('reaction_added')
def handle_reaction_added_event(ack, say, event, client):
    ack()
    for handler in event_handlers:
        handler.check_and_run(client, say, event)


# noop
@app.event('reaction_removed')
def handle_reaction_removed_event(ack, body, say):
    ack()
    pass


# noop
@app.event('app_mention')
def event_app_mention(ack, event, say):
    ack()
    pass


if __name__ == '__main__':
    app.start(3000)
