from typing import Any, Dict, Union
from slack_bolt import Say
from slack_sdk import WebClient

from util import get_prop


class MessageSentEvent:
    def __init__(self, message: str, ts: str):
        self.message = message
        self.ts = ts


def reply_to_question(event: Dict[str, Any], say: Say, _client: WebClient):
    if not is_message_sent_event(event):
        return

    text = get_prop(event, 'text')
    thread_ts = get_prop(event, 'thread_ts') or get_prop(event, 'ts')

    keyword = find_keyword('!', text)
    reply = find_reply(keyword)

    if reply is not None:
        say(text=reply, thread_ts=thread_ts)


def is_message_sent_event(event: Dict[str, Any]):
    if get_prop(event, 'subtype') is not None:  # 'message_sent to channel' == non-subtype
        return False
    elif get_prop(event, 'type') != 'message':
        return False
    elif (get_prop(event, 'thread_ts') or get_prop(event, 'ts')) is None:
        return False

    return True


def find_keyword(keyword_prefix: str, text: str) -> Union[str, None]:
    assert len(keyword_prefix) > 0

    if text is None or keyword_prefix not in text:
        return None

    chunk = text.split(keyword_prefix)
    if len(chunk) < 2:
        return None

    keyword = chunk[1].split(" ")[0]
    if len(keyword) == 0 or keyword[0] == ' ':
        return None

    return keyword.rstrip()


def find_reply(keyword: str) -> Union[str, None]:
    dictionary = {'wifi': '센터필드의 와이파이를 알려줄게. 이름은 `Guest`, 비밀번호는 `BrokenWires@@2019`야!'}
    return dictionary.get(keyword, None)
