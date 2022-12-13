from _pytest.python_api import raises

from service.qna.qna_service import _make_question, _make_dictionary, _find_answer, _tell_answer, _reply_to_question_v2, _find_keyword
from tests.util.mock_slack_client import MockSlackClient


class Test__make_question:
    def test_make_question_without_thread_ts(self):
        event = {'type': 'message', 'thread_ts': '123.45', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword == 'hey'
        assert ts == '123.45'

    def test_make_question_with_ts(self):
        event = {'type': 'message', 'ts': '123.45', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword == 'hey'
        assert ts == '123.45'

    def test_make_question_without_ts_and_thread_ts(self):
        event = {'type': 'message', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None

    def test_make_question_without_type(self):
        event = {'thread_ts': '123.45', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None

    def test_make_question_without_keyword(self):
        event = {'type': 'message', 'ts': '123.45', 'text': '!'}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts == '123.45'


class Test__make_dictionary:
    def test_make_dictionary(self):
        dictionary = _make_dictionary()
        assert dictionary['wifi'] is not None


class Test__find_answer:
    def test_find_answer_with_proper_dictionary_and_keyword(self):
        dictionary = {"question": "answer"}
        answer = _find_answer(dictionary, "question")
        assert answer == "answer"

    def test_find_answer_with_empty_dictionary(self):
        dictionary = {}
        answer = _find_answer(dictionary, "question")
        assert answer is None

    def test_find_answer_with_None_keyword(self):
        dictionary = {"question": "answer"}
        answer = _find_answer(dictionary, None)
        assert answer is None


class Test__tell_answer:
    def test_tell_answer(self):
        slack_client = MockSlackClient()
        _tell_answer(slack_client, "hello", "123.45")
        assert slack_client.is_tell_called is True

    def test_tell_answer_without_text(self):
        slack_client = MockSlackClient()
        _tell_answer(slack_client, None, "123.45")
        assert slack_client.is_tell_called is False

    def test_tell_answer_without_ts(self):
        slack_client = MockSlackClient()
        _tell_answer(slack_client, "hello", None)
        assert slack_client.is_tell_called is False


class Test__reply_to_question_v2:
    def test_reply_to_question_v2(self):
        event = {'type': 'message', 'thread_ts': '123.45', 'text': '!wifi'}
        slack_client = MockSlackClient()
        _reply_to_question_v2(event, slack_client)
        assert slack_client.is_tell_called is True


class Test__find_keyword:
    def test_fail_when_keyword_prefix_is_None(self):
        with raises(TypeError):
            _find_keyword(None, '!random string')

    def test_fail_when_text_is_None(self):
        assert _find_keyword('!', None) is None

    def test_fail_when_keyword_prefix_not_in_text(self):
        assert _find_keyword('!', 'random string') is None

    def test_fail_when_keyword_prefix_on_last_position_in_text(self):
        assert _find_keyword('!', 'random string!') is None

    def test_fail_keyword_is_only_spaces(self):
        assert _find_keyword('!', '!          ') is None

    def test_success_with_one_length_keyword_prefix(self):
        assert _find_keyword('!', 'string!random hello') == 'random'

    def test_success_with_two_length_keyword_prefix(self):
        assert _find_keyword('!!', 'str!!ingrandom hello') == 'ingrandom'

    def test_success_with_keyword_prefix_in_two_position(self):
        assert _find_keyword('!', 'str!ing!random h!ello') == 'ing'

    def test_success_with_two_length_keyword_prefix_in_two_position(self):
        assert _find_keyword('!!', 'str!!ingrand!!om he!!llo') == 'ingrand'
