import logging
from typing import List, Callable, Any, Dict

from slack_bolt import App, Ack, Say
from slack_sdk import WebClient

logger = logging.getLogger(__name__)


def listen_event_with_services(app: App, services: List[Callable]):
    def _call_services(ack: Ack, event: Dict[str, Any], say: Say, web_client: WebClient):
        ack()
        for service in services:
            try:
                service(event, say, web_client)
            except BaseException as ex:
                logger.error(ex)
                say(text=f"예상치 못한 에러가 발생했어! ({ex})")

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
