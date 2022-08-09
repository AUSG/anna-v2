import logging

from slack_bolt import App

import env_bucket
from ask_reply.handler import ArHandler
from offiline_meeting.handler import OmHandler

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("root")

SLACK_BOT_TOKEN = env_bucket.get('SLACK_BOT_TOKEN')
SLACK_SIGNING_SECRET = env_bucket.get('SLACK_SIGNING_SECRET')


app = App(
    token=SLACK_BOT_TOKEN,
    signing_secret=SLACK_SIGNING_SECRET
)


# handler 는 모두 check_and_run(client, say, event) 을 구현해야 한다.
message_channels_event_handlers = [ArHandler()]
@app.event('message')
def handle_message_channels_event(ack, say, event, client):
    ack()
    for handler in reaction_added_event_handlers:
        handler.check_and_run(client, say, event)


# handler 는 모두 check_and_run(client, say, event) 을 구현해야 한다.
reaction_added_event_handlers = [OmHandler()]
@app.event('reaction_added')
def handle_reaction_added_event(ack, say, event, client):
    ack()
    for handler in reaction_added_event_handlers:
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
    app.start(8080)
