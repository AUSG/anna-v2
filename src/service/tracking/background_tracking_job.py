    
import json
from pprint import pprint
from typing import List
from implementation.ausg_db import AUSG_DB
from implementation.slack_client import Message
from slack_bolt import App

import os
def background_tracking_job():

    db = AUSG_DB()
    app = _create_client()
    
    threads = db.read_tracking_threads()
    for thread in threads:
        (channel, ts) = thread
        pprint("new thread: %s, %s" % (channel, ts))
        resp = _get_replies(app, ts=ts, channel=channel)
        db.update_tracking_thread(channel, ts, json.dumps(resp))


def _create_client():
    """
    이렇게도 만들수 있는 줄 몰랐네.. 
    ref: https://api.slack.com/start/building/bolt-python#initialize
    """
    SLACK_BOT_TOKEN = os.environ.get('SLACK_BOT_TOKEN')
    SLACK_SIGNING_SECRET = os.environ.get('SLACK_SIGNING_SECRET')

    return App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)


def _get_replies(app: App, ts: str, channel: str) -> List[Message]:
    resp = app.client.conversations_replies(ts=ts, channel=channel)
    return resp["messages"]
