import logging
import os
import traceback
from typing import List, Callable, cast

from slack_bolt import App, Ack, Say
from slack_sdk import WebClient

from configuration import Configs
from exception import RuntimeException
from util import get_prop, SlackGeneralEvent

logger = logging.getLogger(__name__)

ADMIN_CHANNEL = Configs.ADMIN_CHANNEL

_SERVICES = []


def _get_ts(ex: BaseException, event: SlackGeneralEvent):
    if get_prop(event, 'item', 'thread_ts') is not None:
        return get_prop(event, 'item', 'thread_ts')
    else:
        return get_prop(event, 'item', 'ts')


def _call_services(ack: Ack, event: SlackGeneralEvent, say: Say, web_client: WebClient):
    ack()
    for service in _SERVICES:
        try:
            service(event, say, web_client)
        except BaseException as ex:
            tb = traceback.format_exc()
            err_msg = f"예상치 못한 에러가 발생했어!\n - thread_ts={_get_ts(ex, event)})\n - ex={ex}\n - tb={tb})"
            logger.error(err_msg)
            say(text=err_msg, channel=ADMIN_CHANNEL)


def listen_event_with_services(app: App, services: List[Callable]):
    global _SERVICES
    _SERVICES = services

    @app.event('app_mention')
    def handler_app_mention_event(ack, event, say, client):
        _call_services(ack, event, say, client)

    @app.event('reaction_added')
    def handle_reaction_added_event(ack, event, say, client):
        _call_services(ack, event, say, client)

    @app.event('reaction_removed')
    def handle_reaction_removed_event(ack, event, say, client):
        _call_services(ack, event, say, client)

    @app.event({"type": "message"})
    def handle_message_event(ack, event, say, client):
        _call_services(ack, event, say, client)

    logger.info("모든 리스너 등록 완료")
