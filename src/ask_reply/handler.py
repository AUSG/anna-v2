import pprint
from typing import Dict, Any

from slack_bolt import Say
from slack_sdk import WebClient


class ArHandler:
    def check_and_run(self, web_client: WebClient, say: Say, event: Dict[str, Any]):
        pprint.pprint(event)
        pprint.pprint("=================")
        say("yeah")
