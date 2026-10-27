"""애플리케이션 구성. import만으로 서버나 스케줄러를 시작하지 않는다."""

import logging

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

import bootstrap
from features.bigchat import (
    http as bigchat_http,
    jobs as bigchat_jobs,
    slack as bigchat_slack,
)
from features.community import jobs as community_jobs, slack as community_slack
from shared.slack_events import is_edited_message
from shared.slack_middleware import catch_global_error
from slack_router import classify_mention


@catch_global_error()
def mention_response(event, say, client, dependencies=bootstrap):
    slack_client = dependencies.SlackClient(say, client)
    command = classify_mention(event["text"])
    handler = dependencies.create_mention_handler(command, event, slack_client)
    with dependencies._loading_emoji(slack_client, event):
        return handler.handle_mention()


def create_app(dependencies=bootstrap, *, bolt_app=None):
    if bolt_app is None:
        bolt_app = App(
            token=dependencies.envs.SLACK_BOT_TOKEN,
            signing_secret=dependencies.envs.SLACK_SIGNING_SECRET,
        )
    bigchat_slack.register(bolt_app, dependencies)
    community_slack.register(bolt_app, dependencies)

    @bolt_app.event("app_mention")
    def handle_app_mention_event(ack, event, say, client):
        ack()
        if is_edited_message(event):
            logging.getLogger(__name__).info(
                "Ignoring app_mention from an edited message (ts=%s)", event.get("ts")
            )
            return
        mention_response(event=event, say=say, client=client, dependencies=dependencies)

    flask_app = Flask(__name__)
    handler = SlackRequestHandler(bolt_app)
    flask_app.extensions["slack_app"] = bolt_app

    @flask_app.post("/slack/events")
    def slack_events():
        return handler.handle(request)

    @flask_app.get("/health")
    def health():
        return {"status": "ok"}

    flask_app.register_blueprint(bigchat_http.create_blueprint(dependencies))
    return flask_app


def start_schedulers(dependencies=bootstrap):
    bigchat_jobs.start_scheduler(dependencies)
    community_jobs.start_scheduler(dependencies)
