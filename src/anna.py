import logging

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from config.env_config import envs
from config.log_config import init_logger
from handler.controller import (
    join_bigchat,
    abandon_bigchat,
    announce_new_channel_created,
    mention_response,
    subin_like_response,
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
def handle_app_mention_event(ack, event, say, client):
    ack()
    mention_response(say=say, event=event, client=client)


@app.event("channel_created")
def handle_channel_created_event(ack, event, say, client):
    ack()
    announce_new_channel_created(event=event, say=say, client=client)


@app.event("message")
def handle_message_event(ack, event, say, client):
    ack()
    subin_like_response(event=event, say=say, client=client)


flask_app = Flask(__name__)
slack_request_handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return slack_request_handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    PORT = 8080
    logging.getLogger(__name__).info("Anna wakes up at room %d", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)
