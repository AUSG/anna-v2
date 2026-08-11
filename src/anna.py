import logging
import re

from flask import Flask, Response, abort, request
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
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from slack_sdk import WebClient
from util.bigchat_event import ics_payload, parse_sheet_name, to_ics, verify_ics_token

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


@app.action(re.compile("calendar_.*"))
def handle_calendar_button(ack):
    # 링크 버튼은 URL을 여는 것 외에 서버 동작이 없지만, ack하지 않으면 버튼에 ⚠️가 표시된다
    ack()


flask_app = Flask(__name__)
slack_request_handler = SlackRequestHandler(app)


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return slack_request_handler.handle(request)


@flask_app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


def _fetch_bigchat_intro(channel: str, ts: str) -> str:
    """스레드 첫 글(이벤트 소개글)을 클릭 시점에 읽어온다. 실패해도 ics 제공은 막지 않는다."""
    try:
        web_client = WebClient(token=envs.SLACK_BOT_TOKEN)
        resp = web_client.conversations_replies(channel=channel, ts=ts, limit=1)
        return resp["messages"][0]["text"]
    except Exception as ex:
        logging.getLogger(__name__).warning(f"Failed to fetch bigchat intro: {ex}")
        return ""


@flask_app.route("/bigchat/<int:worksheet_id>/event.ics", methods=["GET"])
def bigchat_ics(worksheet_id: int):
    if not envs.ICS_TOKEN_SECRET:
        abort(404)
    channel = request.args.get("channel", "")
    ts = request.args.get("ts", "")
    if not verify_ics_token(
        envs.ICS_TOKEN_SECRET,
        ics_payload(worksheet_id, channel, ts),
        request.args.get("token", ""),
    ):
        abort(403)

    try:
        sheet_name = GoogleSpreadsheetClient().get_worksheet_title(worksheet_id)
    except Exception as ex:
        logging.getLogger(__name__).warning(
            f"Failed to load worksheet {worksheet_id}: {ex}"
        )
        abort(404)

    event = parse_sheet_name(sheet_name or "")
    if not event:
        abort(404)

    description = _fetch_bigchat_intro(channel, ts) if channel and ts else ""
    return Response(
        to_ics(event, uid=f"bigchat-{worksheet_id}@ausg-anna", description=description),
        mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="event.ics"'},
    )


if __name__ == "__main__":
    PORT = 8080
    logging.getLogger(__name__).info("Anna wakes up at room %d", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)
