"""Bolt 이벤트 등록, ACK와 명령 dispatch. 실제 핸들러의 조립은 anna.py가 담당한다."""

import logging
import re
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol

from slack_sdk import WebClient

from features.bigchat.handlers.create_bigchat_modal import (
    CREATE_BIGCHAT_SHORTCUT_ID,
    CREATE_BIGCHAT_VIEW_ID,
    normalize_shortcut_body,
    normalize_view_body,
)
from integrations.slack import SlackClient
from shared.error_boundary import catch_global_error
from shared.loading_emoji import LoadingEmoji
from shared.mention_handler import MentionHandler
from shared.slack_events import is_edited_message
from shared.utils import search_value
from slack_router import MentionCommand, classify_mention

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlackContext:
    """한 이벤트에만 속하는 값. 앱 전체에서 공유하지 않는다."""

    event: dict
    slack_client: SlackClient
    web_client: WebClient
    ack: Callable

    @property
    def loading_emoji(self) -> LoadingEmoji:
        return LoadingEmoji(
            self.slack_client,
            search_value(self.event, "channel"),
            search_value(self.event, "ts"),
        )


class EventHandler(Protocol):
    def run(self):
        ...


@dataclass(frozen=True)
class SlackHandlers:
    """이벤트를 받을 때 새 핸들러를 만드는 factory 모음."""

    mentions: Mapping[MentionCommand, Callable[[SlackContext], MentionHandler]]
    join_bigchat: Callable[[SlackContext], EventHandler]
    abandon_bigchat: Callable[[SlackContext], EventHandler]
    announce_new_channel_created: Callable[[SlackContext], EventHandler]
    subin_like_response: Callable[[SlackContext], EventHandler]
    open_create_bigchat_modal: Callable[[SlackContext], EventHandler]
    submit_create_bigchat_modal: Callable[[SlackContext], EventHandler]


def register_slack_handlers(app, handlers: SlackHandlers, *, admin_channel: str):
    boundary = catch_global_error(admin_channel=admin_channel)

    @boundary
    def run_event_handler(*, event, say, client, ack, factory):
        context = SlackContext(event, SlackClient(say, client), client, ack)
        factory(context).run()

    @boundary
    def run_mention_handler(*, event, say, client, ack):
        context = SlackContext(event, SlackClient(say, client), client, ack)
        command = classify_mention(event["text"])
        handler = handlers.mentions[command](context)
        # 선택한 하나만 실행하며, 실패하거나 False를 반환해도 다른 명령으로 넘어가지 않는다.
        with context.loading_emoji:
            handler.handle_mention()

    @app.event("reaction_added")
    def handle_reaction_added_event(ack, event, say, client):
        ack()
        run_event_handler(
            event=event, say=say, client=client, ack=ack, factory=handlers.join_bigchat
        )

    @app.event("reaction_removed")
    def handle_reaction_removed_event(ack, event, say, client):
        ack()
        run_event_handler(
            event=event,
            say=say,
            client=client,
            ack=ack,
            factory=handlers.abandon_bigchat,
        )

    @app.event("app_mention")
    def handle_app_mention_event(ack, event, say, client):
        ack()
        if is_edited_message(event):
            logger.info(
                "Ignoring app_mention from an edited message (ts=%s)", event.get("ts")
            )
            return
        run_mention_handler(event=event, say=say, client=client, ack=ack)

    @app.event("channel_created")
    def handle_channel_created_event(ack, event, say, client):
        ack()
        run_event_handler(
            event=event,
            say=say,
            client=client,
            ack=ack,
            factory=handlers.announce_new_channel_created,
        )

    @app.event("message")
    def handle_message_event(ack, event, say, client):
        ack()
        if is_edited_message(event):
            logger.debug("Ignoring edited message event (ts=%s)", event.get("ts"))
            return
        run_event_handler(
            event=event,
            say=say,
            client=client,
            ack=ack,
            factory=handlers.subin_like_response,
        )

    @app.action(re.compile("calendar_.*"))
    def handle_calendar_button(ack):
        # URL을 여는 버튼도 ACK하지 않으면 Slack에 오류 표시가 뜬다.
        ack()

    @app.shortcut(CREATE_BIGCHAT_SHORTCUT_ID)
    def handle_create_bigchat_shortcut(ack, body, say, client):
        ack()
        run_event_handler(
            event=normalize_shortcut_body(body),
            say=say,
            client=client,
            ack=ack,
            factory=handlers.open_create_bigchat_modal,
        )

    @app.view(CREATE_BIGCHAT_VIEW_ID)
    def handle_create_bigchat_view_submission(ack, body, say, client):
        # 모달은 검증 결과에 따라 feature handler가 ACK한다.
        run_event_handler(
            event=normalize_view_body(body),
            say=say,
            client=client,
            ack=ack,
            factory=handlers.submit_create_bigchat_modal,
        )
