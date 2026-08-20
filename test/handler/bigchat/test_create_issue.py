import unittest
from unittest.mock import MagicMock

from test.handler.bigchat.sample_data import create_sample_app_mention_event

from handler.bigchat.create_issue import MAX_TITLE_LEN, CreateIssue
from implementation.github_client import GithubApiError, Issue
from implementation.slack_client import Message

ANNA_ID = "U01BN035Y6L"


def _event(text, in_thread=False):
    event = create_sample_app_mention_event(text)
    if not in_thread:
        # 스레드 밖(채널 최상단)에서의 멘션에는 thread_ts 가 없다
        del event["thread_ts"]
    return event


def _message(user, text):
    return Message(
        ts="1689403100.222939",
        thread_ts="1689403100.222939",
        channel="C03SZTDEDK3",
        user=user,
        text=text,
    )


class CreateIssueTestBase(unittest.TestCase):
    def _build_sut(self, text, in_thread=False, enabled=True):
        self.mock_slack_client = MagicMock()
        self.mock_slack_client.get_permalink.return_value = (
            "https://ausg.slack.com/archives/C03SZTDEDK3/p1689403771805849"
        )
        self.mock_github_client = MagicMock()
        self.mock_github_client.is_enabled.return_value = enabled
        self.mock_github_client.create_issue.return_value = Issue(
            number=42,
            title="빅챗 리마인더가 두 번 와요",
            url="https://github.com/AUSG/anna-v2/issues/42",
        )
        return CreateIssue(
            _event(text, in_thread), self.mock_slack_client, self.mock_github_client
        )

    def _created_issue_kwargs(self):
        return self.mock_github_client.create_issue.call_args.kwargs

    def _public_reply(self):
        return self.mock_slack_client.send_message.call_args.kwargs["msg"]

    def _private_reply(self):
        return (
            self.mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                "msg"
            ]
        )


class TestCanHandle(CreateIssueTestBase):
    def test_can_handle(self):
        assert self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요").can_handle()
        assert self._build_sut(f"<@{ANNA_ID}> 새 이슈 리마인더가 두 번 와요").can_handle()
        assert self._build_sut(f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요").can_handle()
        assert self._build_sut(f"<@{ANNA_ID}> 이슈 등록해줘 리마인더가 두 번 와요").can_handle()
        assert self._build_sut(f"<@{ANNA_ID}> 이슈 파줘 리마인더가 두 번 와요").can_handle()

    def test_can_not_handle(self):
        assert not self._build_sut(f"<@{ANNA_ID}> 안녕").can_handle()
        # 이슈 이야기를 한다고 다 이슈를 만들면 곤란하다
        assert not self._build_sut(f"<@{ANNA_ID}> 그 이슈 어떻게 됐어?").can_handle()
        assert not self._build_sut(f"<@{ANNA_ID}> 이슈 파악해줘").can_handle()
        assert not self._build_sut(
            f"<@{ANNA_ID}> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        ).can_handle()


class TestCreateIssue(CreateIssueTestBase):
    def test_creates_issue_with_title_only(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 빅챗 리마인더가 두 번 와요")

        result = sut.handle_mention()

        assert result is True
        assert self._created_issue_kwargs()["title"] == "빅챗 리마인더가 두 번 와요"
        # 이슈 링크를 스레드에 공개로 알려서, 만들어진 걸 다 같이 볼 수 있게 한다
        assert "https://github.com/AUSG/anna-v2/issues/42" in self._public_reply()
        assert "#42" in self._public_reply()

    def test_second_line_becomes_issue_body(self):
        sut = self._build_sut(
            f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요\n어제 저녁에 DM 이 두 통 왔어.\n재현 100%"
        )

        sut.handle_mention()

        kwargs = self._created_issue_kwargs()
        assert kwargs["title"] == "리마인더가 두 번 와요"
        assert kwargs["body"].startswith("어제 저녁에 DM 이 두 통 왔어.\n재현 100%")

    def test_body_has_permalink_footer(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요")

        sut.handle_mention()

        body = self._created_issue_kwargs()["body"]
        # 슬랙 어느 대화에서 나온 이야기인지 이슈만 보고도 찾아갈 수 있어야 한다
        assert "https://ausg.slack.com/archives/C03SZTDEDK3/p1689403771805849" in body
        assert "UQJ8HQJG5" in body

    def test_body_keeps_going_without_permalink(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요")
        self.mock_slack_client.get_permalink.return_value = None

        result = sut.handle_mention()

        assert result is True
        assert "원문:" not in self._created_issue_kwargs()["body"]

    def test_includes_thread_context(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요", in_thread=True)
        self.mock_slack_client.get_replies.return_value = [
            _message("U0001", "어제 리마인더 두 번 왔는데 저만 그런가요?"),
            _message("U0002", f"저도요 <@{ANNA_ID}>"),
        ]

        sut.handle_mention()

        body = self._created_issue_kwargs()["body"]
        assert "### 슬랙 스레드" in body
        assert "> **U0001**: 어제 리마인더 두 번 왔는데 저만 그런가요?" in body
        # 스레드 인용에서도 멘션 코드는 걷어낸다
        assert "> **U0002**: 저도요" in body

    def test_no_thread_context_outside_thread(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요")

        sut.handle_mention()

        self.mock_slack_client.get_replies.assert_not_called()
        assert "### 슬랙 스레드" not in self._created_issue_kwargs()["body"]

    def test_keeps_going_when_thread_context_fails(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요", in_thread=True)
        self.mock_slack_client.get_replies.side_effect = Exception("boom")

        result = sut.handle_mention()

        assert result is True
        self.mock_github_client.create_issue.assert_called_once()

    def test_drops_punctuation_left_by_the_trigger(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 이슈 만들어줄래? 리마인더가 두 번 와요")

        sut.handle_mention()

        assert self._created_issue_kwargs()["title"] == "리마인더가 두 번 와요"

    def test_truncates_too_long_title(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 " + "가" * 300)

        sut.handle_mention()

        title = self._created_issue_kwargs()["title"]
        assert len(title) == MAX_TITLE_LEN
        assert title.endswith("…")

    def test_escapes_link_text_in_the_reply(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 <script> 태그가 안 먹어요")
        self.mock_github_client.create_issue.return_value = Issue(
            number=42,
            title="<script> 태그가 안 먹어요",
            url="https://github.com/AUSG/anna-v2/issues/42",
        )

        sut.handle_mention()

        # 제목의 <, > 가 그대로 나가면 슬랙 링크 표기가 깨진다
        assert "&lt;script&gt;" in self._public_reply()


class TestRefuses(CreateIssueTestBase):
    def test_shows_usage_without_a_title(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 이슈 만들어줘")

        result = sut.handle_mention()

        assert result is False
        self.mock_github_client.create_issue.assert_not_called()
        assert "제목을 같이 적어줘" in self._private_reply()

    def test_tells_when_github_token_is_missing(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요", enabled=False)

        result = sut.handle_mention()

        assert result is False
        self.mock_github_client.create_issue.assert_not_called()
        assert "깃허브 토큰" in self._private_reply()

    def test_reports_github_error(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요")
        self.mock_github_client.create_issue.side_effect = GithubApiError(
            "깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!"
        )

        result = sut.handle_mention()

        assert result is False
        # 실패는 요청한 사람에게만 알린다 (스레드를 에러로 어지럽히지 않게)
        self.mock_slack_client.send_message.assert_not_called()
        assert "깃허브에 연결하지 못했어" in self._private_reply()
