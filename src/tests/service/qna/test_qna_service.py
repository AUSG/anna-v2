from _pytest.python_api import raises

from implementation import SlackClient
from service.qna.qna_service import (
    _make_question,
    _make_dictionary,
    _find_answer,
    _tell_answer,
    _reply_to_question_v2,
    _find_keyword,
)


class Test__make_question:
    def test_스레드에_남긴_댓글의_이벤트는_ts와_text를_사용해_ts와_keyword를_리턴한다(self):
        event = {"type": "message", "thread_ts": "123.45", "text": "!hey"}
        keyword, ts = _make_question(event)
        assert keyword == "hey"
        assert ts == "123.45"

    def test_채널에_남긴_댓글의_이벤트는_ts와_text를_사용해_ts와_keyword를_리턴한다(self):
        event = {"type": "message", "ts": "123.45", "text": "!hey"}
        keyword, ts = _make_question(event)
        assert keyword == "hey"
        assert ts == "123.45"

    def test_thread_ts와_ts와_text_가_주어지면_ts_인풋은_무시한다(self):
        event = {
            "type": "message",
            "ts": "123.45",
            "thread_ts": "678.90",
            "text": "!hey",
        }

        keyword, ts = _make_question(event)

        assert keyword == "hey"
        assert ts == "678.90"

    def test_ts와_thread_ts가_없다면_keyword와_ts을_리턴하지_않는다(self):
        event = {"type": "message", "text": "!hey"}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None

    def test_메시지_type이_없다면_keyword와_ts을_리턴하지_않는다(self):
        event = {"thread_ts": "123.45", "text": "!hey"}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None

    def test_키워드를_생성하지_못하면_keyword와_ts을_리턴하지_않는다(self):
        event = {"type": "message", "ts": "123.45", "text": "!"}
        keyword, ts = _make_question(event)
        assert keyword is None
        assert ts is None


class Test__make_dictionary:
    def success(self):
        dictionary = _make_dictionary()
        assert dictionary["wifi"] is not None


class Test__find_answer:
    def test_when_keyword_exists_in_dictionary(self):
        dictionary = {"question": "answer"}
        answer = _find_answer(dictionary, "question")
        assert answer == "answer"

    def test_when_keyword_not_exists_in_dictionary(self):
        dictionary = {"question": "answer"}
        answer = _find_answer(dictionary, None)
        assert answer is None

    def test_when_dictionary_is_empty(self):
        dictionary = {}
        answer = _find_answer(dictionary, "question")
        assert answer is None


class Test__tell_answer:
    def test_with_text_and_ts(self, mocker):
        mock_slack_client = self._make_mock_slack_client(mocker)

        _tell_answer(mock_slack_client, "hello", "123.45")

        mock_slack_client.tell.assert_called()

    def test_without_text(self, mocker):
        mock_slack_client = self._make_mock_slack_client(mocker)

        _tell_answer(mock_slack_client, None, "123.45")

        mock_slack_client.tell.assert_not_called()

    def test_without_ts(self, mocker):
        mock_slack_client = self._make_mock_slack_client(mocker)

        _tell_answer(mock_slack_client, "hello", None)

        mock_slack_client.tell.assert_not_called()

    def _make_mock_slack_client(self, mocker):
        mocker.patch.object(SlackClient, "tell")
        mock_slack_client = SlackClient("dummy", "dummy")
        return mock_slack_client


class Test__find_keyword:
    def test_with_keyword_prefix_is_None(self):
        with raises(TypeError):
            _find_keyword(None, "!random string")

    def test_with_text_is_None(self):
        assert _find_keyword("!", None) is None

    def test_with_keyword_prefix_not_in_text(self):
        assert _find_keyword("!", "random string") is None

    def test_with_keyword_prefix_on_last_position_in_text(self):
        assert _find_keyword("!", "random string!") is None

    def test_with_whitespaces_keyword(self):
        assert _find_keyword("!", "!          ") is None

    def test_with_one_length_keyword_prefix(self):
        assert _find_keyword("!", "string!random hello") == "random"

    def test_with_two_length_keyword_prefix(self):
        assert _find_keyword("!!", "str!!ingrandom hello") == "ingrandom"

    def test_with_keyword_prefix_in_two_position(self):
        assert _find_keyword("!", "str!ing!random h!ello") == "ing"

    def test_with_two_length_keyword_prefix_in_two_position(self):
        assert _find_keyword("!!", "str!!ingrand!!om he!!llo") == "ingrand"


class Test__reply_to_question_v2:
    def test_with_perfect_condition(self, mocker):
        mock_slack_client = self._make_mock_slack_client(mocker)
        event = {"type": "message", "thread_ts": "123.45", "text": "!wifi"}

        _reply_to_question_v2(event, mock_slack_client)

        mock_slack_client.tell.assert_called()

    def _make_mock_slack_client(self, mocker):
        mocker.patch.object(SlackClient, "tell")
        mock_slack_client = SlackClient("dummy", "dummy")
        return mock_slack_client
