from typing import Dict, Any

from slack_bolt import Say
from slack_sdk import WebClient

from ask_reply.service import ArService
from event import MessageSentEvent


class ArHandler:
    def check_and_run(self, web_client: WebClient, say: Say, event: Dict[str, Any]):
        ar_svc = self._inject_dependencies(event, say)

        ar_svc.reply()

    def _inject_dependencies(self, event, say):
        msg = event.get('text', "")
        ts = event.get('thread_ts', None) or event['ts']
        event = MessageSentEvent(msg, ts)
        ar_svc = ArService(say, event)
        return ar_svc

