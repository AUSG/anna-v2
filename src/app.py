"""애플리케이션 구성. import만으로 서버나 스케줄러를 시작하지 않는다."""

import logging

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from features.bigchat import (
    http as bigchat_http,
    jobs as bigchat_jobs,
    slack as bigchat,
)
from features.bigchat.services.commands import CreateBigchat, Reminder
from features.bot_commands import slack as bot_commands
from features.bot_commands.models import Empty, Help, Shuffle
from features.community import jobs as community_jobs, slack as community
from features.issues import slack as issues
from features.issues.models import CreateIssue
from features.questions import slack as questions
from features.questions.models import Question
from runtime import Runtime
from shared.error_boundary import report_failure
from shared.gateways import SlackGateway
from shared.loading_emoji import with_loading_emoji
from shared.slack_events import MentionEvent, is_edited_message
from slack_router import MentionCommand, parse_mention

logger = logging.getLogger(__name__)


def dispatch_mention(
    command: MentionCommand, event: MentionEvent, slack: SlackGateway, runtime: Runtime
) -> bool:
    """선택된 명령만 실행한다. 실패하거나 False 를 반환해도 다른 명령으로 넘어가지 않는다."""
    settings = runtime.settings
    match command:
        case Help():
            return bot_commands.show_help(event, slack)
        case Shuffle():
            return bot_commands.shuffle_users(command, event, slack)
        case Question():
            return questions.answer_question(
                command, event, slack, runtime.qa(), assistant_id=settings.ANNA_ID
            )
        case CreateIssue():
            return issues.create_issue(command, event, slack, runtime.github())
        case CreateBigchat():
            return bigchat.create_from_mention(command, event, slack, runtime)
        case Reminder():
            return bigchat.remind_now(command, event, slack, runtime)
        case Empty():
            return bot_commands.unknown_command(event, slack)
    raise ValueError(f"Unknown mention command: {command!r}")


def mention_response(
    event: MentionEvent, slack: SlackGateway, runtime: Runtime
) -> bool:
    command = parse_mention(event.text, runtime.settings.ANNA_ID)
    return with_loading_emoji(
        slack,
        event.channel,
        event.ts,
        lambda: dispatch_mention(command, event, slack, runtime),
    )


def create_app(runtime: Runtime, *, bolt_app=None):
    settings = runtime.settings
    if bolt_app is None:
        bolt_app = App(
            token=settings.SLACK_BOT_TOKEN, signing_secret=settings.SLACK_SIGNING_SECRET
        )
    bigchat.register(bolt_app, runtime)
    community.register(bolt_app, runtime)

    @bolt_app.event("app_mention")
    def handle_app_mention_event(ack, event, client):
        ack()
        # 이미 있던 멘션을 고쳐도 이벤트가 다시 온다. 명령이 두 번 실행되지 않도록 여기서 끊는다
        if is_edited_message(event):
            logger.info(
                "Ignoring app_mention from an edited message (ts=%s)", event.get("ts")
            )
            return
        slack = runtime.slack_client(client)
        try:
            mention_response(MentionEvent.from_payload(event), slack, runtime)
        except Exception as exc:
            report_failure(slack, settings.ADMIN_CHANNEL, event, exc)

    flask_app = Flask(__name__)
    handler = SlackRequestHandler(bolt_app)
    flask_app.extensions["slack_app"] = bolt_app

    @flask_app.post("/slack/events")
    def slack_events():
        return handler.handle(request)

    @flask_app.get("/health")
    def health():
        return {"status": "ok"}

    flask_app.register_blueprint(bigchat_http.create_blueprint(runtime))
    return flask_app


def start_schedulers(runtime: Runtime):
    bigchat_jobs.start_scheduler(runtime)
    community_jobs.start_scheduler(runtime)
