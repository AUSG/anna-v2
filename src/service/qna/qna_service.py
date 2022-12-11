from typing import Union

from slack_bolt import Say
from slack_sdk import WebClient

from util import get_prop, SlackGeneralEvent


class MessageSentEvent:
    def __init__(self, message: str, ts: str):
        self.message = message
        self.ts = ts


def make_question(event):
    """
    Returns:
        keyword, ts
    """
    event_type = get_prop(event, 'type')
    ts = get_prop(event, 'thread_ts') or get_prop(event, 'ts')

    if event_type != 'message' or ts is None:
        return None, None

    return find_keyword('!', get_prop(event, 'text')), ts


def make_dictionary():
    dictionary = {'wifi': '센터필드의 와이파이를 알려줄게. 이름은 `Guest`, 비밀번호는 `BrokenWires@@2019`야!'}
    return dictionary


def find_answer(dictionary, keyword):
    return None if keyword is None else dictionary.get(keyword, None)


def tell_answer(slack_client, text, ts):
    if text is None or ts is None:
        return
    slack_client.tell(text=text, thread_ts=ts)


def reply_to_question_v2(event, slack_client):
    keyword, ts = make_question(event)
    dictionary = make_dictionary()
    answer = find_answer(dictionary, keyword)
    tell_answer(slack_client, answer, ts)


def reply_to_question(event: SlackGeneralEvent, say: Say, _client: WebClient):
    if not is_message_sent_event(event):
        return

    text = get_prop(event, 'text')
    thread_ts = get_prop(event, 'thread_ts') or get_prop(event, 'ts')

    keyword = find_keyword('!', text)
    reply = find_reply(keyword)

    if reply is not None:
        say(text=reply, thread_ts=thread_ts)


def is_message_sent_event(event: SlackGeneralEvent):
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
