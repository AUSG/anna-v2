from typing import Union

from slack_bolt import Say
from slack_sdk import WebClient

from implementation import SlackClient
from util import get_prop, SlackGeneralEvent


def _make_question(event):
    """
    Note:
        thread_ts, ts 가 둘 다 제공되었다면 thread_ts 가 우선적으로 적용된다.

        적절한 question을 추출하지 못한다면 (None, None)을 리턴한다.

    Returns:
        keyword, ts
    """
    event_type = get_prop(event, 'type')
    ts = get_prop(event, 'thread_ts') or get_prop(event, 'ts')

    if event_type != 'message' or ts is None:
        return None, None

    keyword = _find_keyword('!', get_prop(event, 'text'))
    if keyword and ts:
        return keyword, ts
    else:
        return None, None


def _find_keyword(keyword_prefix, text):
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


def _make_dictionary():
    dictionary = {'wifi': '센터필드의 와이파이를 알려줄게. 이름은 `Guest`, 비밀번호는 `BrokenWires@@2019`야!'}
    return dictionary


def _find_answer(dictionary, keyword):
    return None if keyword is None else dictionary.get(keyword, None)


def _tell_answer(slack_client, text, ts):
    if text is None or ts is None:
        return
    slack_client.tell(text=text, thread_ts=ts)


def _reply_to_question_v2(event, slack_client):
    keyword, ts = _make_question(event)
    dictionary = _make_dictionary()
    answer = _find_answer(dictionary, keyword)
    _tell_answer(slack_client, answer, ts)


def reply_to_question(event: SlackGeneralEvent, say: Say, client: WebClient):  # TODO: 시그니처 일괄 변경: say/client -> SlackClient (모든 services 한번에 바꿔야 함)
    _reply_to_question_v2(event, SlackClient(say, client))
