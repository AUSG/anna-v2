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
    remind_bigchat,
    subin_like_response,
)
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from slack_sdk import WebClient
from util.bigchat_event import (
    KST,
    calendar_payload,
    parse_sheet_name,
    to_ics,
    verify_calendar_token,
)
from util.daily_scheduler import DailyScheduler

init_logger()

app = App(token=envs.SLACK_BOT_TOKEN, signing_secret=envs.SLACK_SIGNING_SECRET)

# 빅챗 전날 저녁 6시(KST)에 신청자들에게 리마인더 DM 을 보낸다
if envs.BIGCHAT_REMINDER_ENABLED:
    DailyScheduler(
        job=remind_bigchat, hour=18, minute=0, tz=KST, name="bigchat-reminder"
    ).start()
    logging.getLogger(__name__).info(
        "Bigchat reminder scheduler started (daily 18:00 KST)"
    )


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
    """스레드 첫 글(이벤트 소개글)을 클릭 시점에 읽어온다. 실패해도 캘린더 제공은 막지 않는다."""
    if not channel or not ts:
        return ""
    try:
        web_client = WebClient(token=envs.SLACK_BOT_TOKEN)
        resp = web_client.conversations_replies(channel=channel, ts=ts, limit=1)
        return resp["messages"][0]["text"]
    except Exception as ex:
        logging.getLogger(__name__).warning(f"Failed to fetch bigchat intro: {ex}")
        return ""


def _fetch_permalink(channel: str, ts: str) -> str:
    """원본 메시지 permalink를 클릭 시점에 조회한다. 실패해도 캘린더 제공은 막지 않는다."""
    if not channel or not ts:
        return ""
    try:
        web_client = WebClient(token=envs.SLACK_BOT_TOKEN)
        resp = web_client.chat_getPermalink(channel=channel, message_ts=ts)
        return resp["permalink"]
    except Exception as ex:
        logging.getLogger(__name__).warning(f"Failed to fetch permalink: {ex}")
        return ""


def _build_calendar_description(channel: str, ts: str) -> str:
    """gcal 본문과 같은 포맷: 맨 앞에 permalink, 그 아래 소개글 (ics는 길이 제한이 없어 전문)."""
    parts = []
    permalink = _fetch_permalink(channel, ts)
    if permalink:
        parts.append(f"슬랙에서 소개글 보기: {permalink}")
    intro = _fetch_bigchat_intro(channel, ts)
    if intro:
        parts.append(intro)
    return "\n\n".join(parts)


def _load_bigchat_calendar_context(worksheet_id: int):
    """ics 다운로드의 검증/조회 경로. 반환: (event, description)"""
    if not envs.ICS_TOKEN_SECRET:
        abort(404)
    channel = request.args.get("channel", "")
    ts = request.args.get("ts", "")
    if not verify_calendar_token(
        envs.ICS_TOKEN_SECRET,
        calendar_payload(worksheet_id, channel, ts),
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

    return event, _build_calendar_description(channel, ts)


@flask_app.route("/bigchat/<int:worksheet_id>/event.ics", methods=["GET"])
def bigchat_ics(worksheet_id: int):
    event, description = _load_bigchat_calendar_context(worksheet_id)
    return Response(
        to_ics(event, uid=f"bigchat-{worksheet_id}@ausg-anna", description=description),
        mimetype="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="event.ics"'},
    )


if __name__ == "__main__":
    PORT = 8080
    logging.getLogger(__name__).info("Anna wakes up at room %d", PORT)
    flask_app.run(host="0.0.0.0", port=PORT)
