from service.qna.qna_service import make_question, make_dictionary, find_answer, tell_answer, reply_to_question_v2
from tests.util.mock_slack_client import MockSlackClient


def test_make_question_without_thread_ts():
    event = {'type': 'message', 'thread_ts': '123.45', 'text': '!hey'}
    keyword, ts = make_question(event)
    assert keyword == 'hey'
    assert ts == '123.45'


def test_make_question_with_ts():
    event = {'type': 'message', 'ts': '123.45', 'text': '!hey'}
    keyword, ts = make_question(event)
    assert keyword == 'hey'
    assert ts == '123.45'


def test_make_question_without_ts_and_thread_ts():
    event = {'type': 'message', 'text': '!hey'}
    keyword, ts = make_question(event)
    assert keyword is None
    assert ts is None


def test_make_question_without_type():
    event = {'thread_ts': '123.45', 'text': '!hey'}
    keyword, ts = make_question(event)
    assert keyword is None
    assert ts is None


def test_make_question_without_keyword():
    event = {'type': 'message', 'ts': '123.45', 'text': '!'}
    keyword, ts = make_question(event)
    assert keyword is None
    assert ts == '123.45'


###


def test_make_dictionary():
    dictionary = make_dictionary()
    assert dictionary['wifi'] is not None


###


def test_find_answer_with_proper_dictionary_and_keyword():
    dictionary = {"question": "answer"}
    answer = find_answer(dictionary, "question")
    assert answer == "answer"


def test_find_answer_with_empty_dictionary():
    dictionary = {}
    answer = find_answer(dictionary, "question")
    assert answer is None


def test_find_answer_with_None_keyword():
    dictionary = {"question": "answer"}
    answer = find_answer(dictionary, None)
    assert answer is None


###


def test_tell_answer():
    slack_client = MockSlackClient()
    tell_answer(slack_client, "hello", "123.45")
    assert slack_client.is_tell_called is True


def test_tell_answer_without_text():
    slack_client = MockSlackClient()
    tell_answer(slack_client, None, "123.45")
    assert slack_client.is_tell_called is False


def test_tell_answer_without_ts():
    slack_client = MockSlackClient()
    tell_answer(slack_client, "hello", None)
    assert slack_client.is_tell_called is False


###


def test_reply_to_question_v2():
    event = {'type': 'message', 'thread_ts': '123.45', 'text': '!wifi'}
    slack_client = MockSlackClient()
    reply_to_question_v2(event, slack_client)
    assert slack_client.is_tell_called is True
