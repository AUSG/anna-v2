import logging
from dataclasses import dataclass
from implementation.ausg_db import AUSG_DB
from implementation.slack_client import SlackClient
from slack_bolt import Say
from slack_sdk import WebClient

from util.utils import SlackGeneralEvent, get_prop

logger = logging.getLogger(__name__)

TRACKING_EVENT_NAME='tracking_on'

@dataclass
class TrackingEvent:
    channel: str
    ts: str
    event_type: str # ON / OFF


def track_thread(event: SlackGeneralEvent, say: Say, web_client: WebClient):
    tracking_event = get_tracking_event(event, say, web_client)
    if tracking_event is None:
        return

    change_tracking_status(tracking_event)
    say_for_complete(tracking_event, say, web_client)


## Sample
# {'event_ts': '1666419722.000600',
#  'item': {'channel': 'C03SZTDEDK3',
#           'ts': '1666419708.644459',
#           'type': 'message'},
#  'item_user': 'UQJ8HQJG5',
#  'reaction': 'heart',
#  'type': 'reaction_added',
#  'user': 'UQJ8HQJG5'}
def get_tracking_event(event: SlackGeneralEvent, say: Say, web_client: WebClient):
    if not (get_prop(event, "type") in ('reaction_added', 'reaction_removed') and \
        get_prop(event, "reaction") == TRACKING_EVENT_NAME and \
        get_prop(event, "item", "type") == "message" and \
        get_prop(event, "item", "channel") is not None and \
        get_prop(event, "item", "ts") is not None):
        return None

    
    channel = get_prop(event, "item", "channel")
    ts = get_prop(event, "item", "ts")
    event_type = get_prop(event, "type")

    emojies = SlackClient(say, web_client).get_emojis(channel, ts)
    cnt = 0
    for emoji in emojies:
        if emoji.name == TRACKING_EVENT_NAME:
            cnt+=1
    
    if cnt == 1 and event_type == "reaction_added":
        return TrackingEvent(channel, ts, "ON")
    elif cnt == 0 and event_type == "reaction_removed":
        return TrackingEvent(channel, ts, "OFF")
    else:
        return None



def change_tracking_status(tracking_event: TrackingEvent):
    db = AUSG_DB()
    if tracking_event.event_type == "ON":
        db.insert_tracking_thread(tracking_event.channel, tracking_event.ts)
    elif tracking_event.event_type == "OFF":
        db.delete_tracking_thread(tracking_event.channel, tracking_event.ts)


def say_for_complete(tracking_event: TrackingEvent, say:Say, web_client:WebClient):
    sc = SlackClient(say, web_client)
    if tracking_event.event_type == "ON":
        sc.tell("이제부터 이 스레드를 트래킹할게. 이 위에 있는 내용도 모두 아카이빙될거야!", tracking_event.ts)
    elif tracking_event.event_type == "OFF":
        sc.tell("이제 이 스레드를 트래킹 하지않아. 기존에 아카이빙 된 데이터도 모두 삭제되었어!", tracking_event.ts)