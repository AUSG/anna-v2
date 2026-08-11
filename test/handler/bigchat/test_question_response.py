import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.help_response import HelpResponse
from handler.bigchat.mention_response import MentionResponse
from handler.bigchat.question_response import QuestionResponse
from handler.bigchat.simple_response import SimpleResponse


def _make(text, require_prefix=True):
    event = create_sample_app_mention_event(text)
    slack_client = MagicMock()
    slack_client.get_replies.return_value = []
    qa_client = MagicMock()
    qa_client.chat.return_value = "답변이야!"
    sut = QuestionResponse(
        event, slack_client, qa_client, require_prefix=require_prefix
    )
    return sut, slack_client, qa_client


class TestQuestionResponse(unittest.TestCase):
    def test_explicit_prefix(self):
        sut, slack_client, qa_client = _make("<@U01BN035Y6L> q) RAG가 뭐야")

        assert sut.can_handle() is True
        assert sut.handle_mention() is True
        assert qa_client.chat.call_args.kwargs["question"] == "RAG가 뭐야"
        slack_client.send_message.assert_called_once()

    def test_prefix_mode_ignores_plain_text(self):
        sut, _, _ = _make("<@U01BN035Y6L> RAG가 뭐야")

        assert sut.can_handle() is False

    def test_implicit_mode_takes_whole_text_as_question(self):
        sut, slack_client, qa_client = _make(
            "<@U01BN035Y6L> RAG가 뭐야", require_prefix=False
        )

        assert sut.can_handle() is True
        assert sut.handle_mention() is True
        assert qa_client.chat.call_args.kwargs["question"] == "RAG가 뭐야"

    def test_implicit_mode_skips_empty_mention(self):
        sut, _, _ = _make("<@U01BN035Y6L>", require_prefix=False)

        assert sut.can_handle() is False  # 빈 멘션은 SimpleResponse 폴백으로 넘어간다


class TestMentionRouting(unittest.TestCase):
    """controller.mention_response 와 동일한 체인 구성으로 라우팅을 검증한다."""

    def _run_chain(self, text):
        event = create_sample_app_mention_event(text)
        slack_client = MagicMock()
        slack_client.get_replies.return_value = []
        qa_client = MagicMock()
        qa_client.chat.return_value = "답변이야!"
        question = QuestionResponse(event, slack_client, qa_client)
        help_response = HelpResponse(event, slack_client)
        question_fallback = QuestionResponse(
            event, slack_client, qa_client, require_prefix=False
        )
        simple = SimpleResponse(event, slack_client)
        MentionResponse([question, help_response, question_fallback], simple).run()
        return slack_client, qa_client

    def test_plain_mention_goes_to_qa(self):
        _, qa_client = self._run_chain("<@U01BN035Y6L> 다음 빅챗 언제야?")

        assert qa_client.chat.call_args.kwargs["question"] == "다음 빅챗 언제야?"

    def test_command_wins_over_implicit_question(self):
        slack_client, qa_client = self._run_chain("<@U01BN035Y6L> 도움말 보여줘")

        qa_client.chat.assert_not_called()
        assert "사용할 수 있는 명령어야" in slack_client.send_message.call_args.kwargs["msg"]

    def test_explicit_prefix_wins_over_command(self):
        _, qa_client = self._run_chain("<@U01BN035Y6L> q) 도움말 기능은 어떻게 구현돼있어?")

        assert qa_client.chat.call_args.kwargs["question"] == "도움말 기능은 어떻게 구현돼있어?"

    def test_empty_mention_falls_back_to_simple(self):
        slack_client, qa_client = self._run_chain("<@U01BN035Y6L>")

        qa_client.chat.assert_not_called()
        assert "앗, 잘못입력한 것 같아" in slack_client.send_message.call_args.kwargs["msg"]
