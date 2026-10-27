"""커뮤니티 새 글과 채널 생성 이벤트 진입점."""

import logging

from features.community.services.announcements import AnnounceNewChannelCreated
from features.community.services.auto_reply import SubinLikeResponse
from shared.slack_events import is_edited_message
from shared.slack_middleware import catch_global_error


@catch_global_error()
def announce_new_channel_created(event, say, client, dependencies):
    AnnounceNewChannelCreated(event, dependencies.SlackClient(say, client)).run()


@catch_global_error()
def subin_like_response(event, say, client, dependencies):
    SubinLikeResponse(
        event,
        dependencies.SlackClient(say, client),
        dependencies._get_qa_client(),
        anna_id=dependencies.envs.ANNA_ID,
    ).run()


def register(app, dependencies):
    @app.event("channel_created")
    def handle_channel_created_event(ack, event, say, client):
        ack()
        announce_new_channel_created(
            event=event, say=say, client=client, dependencies=dependencies
        )

    @app.event("message")
    def handle_message_event(ack, event, say, client):
        ack()
        if is_edited_message(event):
            logging.getLogger(__name__).debug(
                "Ignoring edited message event (ts=%s)", event.get("ts")
            )
            return
        subin_like_response(
            event=event, say=say, client=client, dependencies=dependencies
        )
