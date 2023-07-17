import logging

from slack_bolt import App

from config.env_config import envs
from config.log_config import init_logger
from handler.bigchat import (
    join_bigchat,
    simple_response,
    abandon_bigchat,
    create_bigchat_sheet,
)

init_logger()

app = App(token=envs.SLACK_BOT_TOKEN, signing_secret=envs.SLACK_SIGNING_SECRET)


@app.event("reaction_added")
def handle_reaction_added_event(ack, event, say, client):
    ack()
    join_bigchat(event=event, say=say, client=client)


@app.event("reaction_removed")
def handle_reaction_removed_event(ack, event, say, client):
    ack()
    abandon_bigchat(event=event, say=say, client=client)


@app.event("app_mention")
def handle_app_mention_events(ack, event, say, client):
    ack()
    simple_response(event=event, say=say, client=client)
    create_bigchat_sheet(event=event, say=say, client=client)


if __name__ == "__main__":
    PORT = 8080
    logging.getLogger(__name__).info("Anna wakes up at room %d", PORT)
    app.start(PORT)
