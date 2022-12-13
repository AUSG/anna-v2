from _pytest.python_api import raises

from service.qna.qna_service import _make_question, _make_dictionary, _find_answer, _tell_answer, _reply_to_question_v2, _find_keyword
from tests.util.mock_slack_client import MockSlackClient


def test_make_question_without_thread_ts():
    event = {'type': 'message', 'thread_ts': '123.45', 'text': '!hey'}
    keyword, ts = _make_question(event)
    assert keyword == 'hey'
    assert ts == '123.45'


def test_make_question_with_ts():
    event = {'type': 'message', 'ts': '123.45', 'text': '!hey'}
    keyword, ts = _make_question(event)
    assert keyword == 'hey'
    assert ts == '123.45'


def test_make_question_without_ts_and_thread_ts():
    event = {'type': 'message', 'text': '!hey'}
    keyword, ts = _make_question(event)
    assert keyword is None
    assert ts is None


def test_make_question_without_type():
    event = {'thread_ts': '123.45', 'text': '!hey'}
    keyword, ts = _make_question(event)
    assert keyword is None
    assert ts is None


def test_make_question_without_keyword():
    event = {'type': 'message', 'ts': '123.45', 'text': '!'}
    keyword, ts = _make_question(event)
    assert keyword is None
    assert ts == '123.45'


###


def test_make_dictionary():
    dictionary = _make_dictionary()
    assert dictionary['wifi'] is not None


###


def test_find_answer_with_proper_dictionary_and_keyword():
    dictionary = {"question": "answer"}
    answer = _find_answer(dictionary, "question")
    assert answer == "answer"


def test_find_answer_with_empty_dictionary():
    dictionary = {}
    answer = _find_answer(dictionary, "question")
    assert answer is None


def test_find_answer_with_None_keyword():
    dictionary = {"question": "answer"}
    answer = _find_answer(dictionary, None)
    assert answer is None


###


def test_tell_answer():
    slack_client = MockSlackClient()
    _tell_answer(slack_client, "hello", "123.45")
    assert slack_client.is_tell_called is True


def test_tell_answer_without_text():
    slack_client = MockSlackClient()
    _tell_answer(slack_client, None, "123.45")
    assert slack_client.is_tell_called is False


def test_tell_answer_without_ts():
    slack_client = MockSlackClient()
    _tell_answer(slack_client, "hello", None)
    assert slack_client.is_tell_called is False


###


def test_reply_to_question_v2():
    event = {'type': 'message', 'thread_ts': '123.45', 'text': '!wifi'}
    slack_client = MockSlackClient()
    _reply_to_question_v2(event, slack_client)
    assert slack_client.is_tell_called is True


###


def test_fail_when_keyword_prefix_is_None():
    with raises(TypeError):
        _find_keyword(None, '!random string')


def test_fail_when_text_is_None():
    assert _find_keyword('!', None) is None


def test_fail_when_keyword_prefix_not_in_text():
    assert _find_keyword('!', 'random string') is None


def test_fail_when_keyword_prefix_on_last_position_in_text():
    assert _find_keyword('!', 'random string!') is None


def test_fail_keyword_is_only_spaces():
    assert _find_keyword('!', '!          ') is None


def test_success_with_one_length_keyword_prefix():
    assert _find_keyword('!', 'string!random hello') == 'random'


def test_success_with_two_length_keyword_prefix():
    assert _find_keyword('!!', 'str!!ingrandom hello') == 'ingrandom'


def test_success_with_keyword_prefix_in_two_position():
    assert _find_keyword('!', 'str!ing!random h!ello') == 'ing'


def test_success_with_two_length_keyword_prefix_in_two_position():
    assert _find_keyword('!!', 'str!!ingrand!!om he!!llo') == 'ingrand'
