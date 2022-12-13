from _pytest.python_api import raises

from service.qna.qna_service import _make_question, _make_dictionary, _find_answer, _tell_answer, _reply_to_question_v2, _find_keyword
from tests.util.mock_slack_client import MockSlackClient


class Test__make_question:
    def success_with_thread_ts_and_type_and_text(self):
        event = {'type': 'message', 'thread_ts': '123.45', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword == 'hey'
        assert ts == '123.45'

    def success_with_ts_and_type_and_text(self):
        event = {'type': 'message', 'ts': '123.45', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword == 'hey'
        assert ts == '123.45'

    def success_with_ts_and_thread_ts_and_type_and_text(self):
        event = {'type': 'message', 'ts': '123.45', 'thread_ts': '678.90', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword == 'hey'
        assert ts == '678.90'

    def success_without_ts_and_thread_ts(self):
        event = {'type': 'message', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None

    def success_without_type(self):
        event = {'thread_ts': '123.45', 'text': '!hey'}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None

    def success_without_keyword(self):
        event = {'type': 'message', 'ts': '123.45', 'text': '!'}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None


class Test__make_dictionary:
    def success(self):
        dictionary = _make_dictionary()
        assert dictionary['wifi'] is not None


class Test__find_answer:
    def success_when_keyword_exists_in_dictionary(self):
        dictionary = {"question": "answer"}
        answer = _find_answer(dictionary, "question")
        assert answer == "answer"

    def success_when_keyword_not_exists_in_dictionary(self):
        dictionary = {"question": "answer"}
        answer = _find_answer(dictionary, None)
        assert answer is None

    def success_when_dictionary_is_empty(self):
        dictionary = {}
        answer = _find_answer(dictionary, "question")
        assert answer is None


class Test__tell_answer:
    def success_with_text_and_ts(self):
        slack_client = MockSlackClient()
        _tell_answer(slack_client, "hello", "123.45")
        assert slack_client.is_tell_called is True

    def success_without_text(self):
        slack_client = MockSlackClient()
        _tell_answer(slack_client, None, "123.45")
        assert slack_client.is_tell_called is False

    def success_without_ts(self):
        slack_client = MockSlackClient()
        _tell_answer(slack_client, "hello", None)
        assert slack_client.is_tell_called is False


class Test__find_keyword:
    def fail_with_keyword_prefix_is_None(self):
        with raises(TypeError):
            _find_keyword(None, '!random string')

    def fail_with_text_is_None(self):
        assert _find_keyword('!', None) is None

    def fail_with_keyword_prefix_not_in_text(self):
        assert _find_keyword('!', 'random string') is None

    def fail_with_keyword_prefix_on_last_position_in_text(self):
        assert _find_keyword('!', 'random string!') is None

    def fail_with_whitespaces_keyword(self):
        assert _find_keyword('!', '!          ') is None

    def success_with_one_length_keyword_prefix(self):
        assert _find_keyword('!', 'string!random hello') == 'random'

    def success_with_two_length_keyword_prefix(self):
        assert _find_keyword('!!', 'str!!ingrandom hello') == 'ingrandom'

    def success_with_keyword_prefix_in_two_position(self):
        assert _find_keyword('!', 'str!ing!random h!ello') == 'ing'

    def success_with_two_length_keyword_prefix_in_two_position(self):
        assert _find_keyword('!!', 'str!!ingrand!!om he!!llo') == 'ingrand'


class Test__reply_to_question_v2:
    def success_with_perfect_condition(self):
        event = {'type': 'message', 'thread_ts': '123.45', 'text': '!wifi'}
        slack_client = MockSlackClient()
        _reply_to_question_v2(event, slack_client)
        assert slack_client.is_tell_called is True
