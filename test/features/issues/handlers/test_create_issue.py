import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call

from test.fixtures.slack_events import create_sample_app_mention_event

from features.issues.handlers.create_issue import CreateIssue
from integrations.github import GithubApiError, Issue
from integrations.slack import Message

ANNA_ID = "U01BN035Y6L"
FOOTER = "---\n슬랙에서 `UQJ8HQJG5` 가 안나에게 요청해서 만들어진 이슈야."
LINKED_FOOTER = (
    FOOTER + "\n원문: https://ausg.slack.com/archives/C03SZTDEDK3/p1689403771805849"
)
ENABLED = call.github.is_enabled()
THREAD = call.slack.get_replies(channel="C03SZTDEDK3", thread_ts="1689403100.222939")
PERMALINK = call.slack.get_permalink("C03SZTDEDK3", "1689403771.805849")
CHANNEL_LOOKUPS = [ENABLED, PERMALINK]
THREADED_LOOKUPS = [ENABLED, THREAD, PERMALINK]
# 이슈 링크를 스레드에 공개로 알려서, 만들어진 걸 다 같이 볼 수 있게 한다
PUBLIC_REPLY = call.slack.send_message(
    msg="이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/42|#42 빅챗 리마인더가 두 번 와요>",
    ts="1689403771.805849",
)
USAGE_REPLY = call.slack.send_message_only_visible_to_user(
    msg="내 레포에 이슈를 만들어줄게. 제목을 같이 적어줘!"
    "\n- `새로운 이슈 <제목>`: 제목만으로 이슈를 만들어"
    "\n- 둘째 줄부터 쓴 내용은 이슈 본문이 돼"
    "\n- 스레드 안에서 부르면 그 스레드 대화도 본문에 같이 넣어둘게"
    "\n예) `새로운 이슈 빅챗 리마인더가 두 번 와요`",
    channel="C03SZTDEDK3",
    ts="1689403771.805849",
    user_id="UQJ8HQJG5",
)
DISABLED_REPLY = call.slack.send_message_only_visible_to_user(
    msg="깃허브 토큰이 설정되지 않아서 이슈를 만들 수 없어. 운영진에게 알려줘!",
    channel="C03SZTDEDK3",
    ts="1689403771.805849",
    user_id="UQJ8HQJG5",
)
SUCCESS_LOG = "INFO:features.issues.handlers.create_issue:Issue #42 created by UQJ8HQJG5: 빅챗 리마인더가 두 번 와요"
THREAD_WARNING = (
    "WARNING:features.issues.handlers.create_issue:Failed to fetch thread context for the issue body: "
    "스레드 실패 🐍"
)
LINK_WARNING = "WARNING:features.issues.handlers.create_issue:Failed to get permalink for the issue body: 링크 실패 🧪"


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
        self.calls = self._track_calls()
        return CreateIssue(
            _event(text, in_thread), self.mock_slack_client, self.mock_github_client
        )

    def _track_calls(self):
        calls = MagicMock()
        calls.attach_mock(self.mock_slack_client, "slack")
        calls.attach_mock(self.mock_github_client, "github")
        return calls


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
    def test_exact_body_and_success_call_order(self):
        for name, (text, title, replies, body) in {
            "title-only": (
                f"<@{ANNA_ID}> 새로운 이슈 빅챗 리마인더가 두 번 와요",
                "빅챗 리마인더가 두 번 와요",
                None,
                LINKED_FOOTER,
            ),
            "lf-body": (
                f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요\n어제 저녁에 DM 이 두 통 왔어.\n재현 100%",
                "리마인더가 두 번 와요",
                None,
                "어제 저녁에 DM 이 두 통 왔어.\n재현 100%\n\n" + LINKED_FOOTER,
            ),
            # 스레드 인용에서도 멘션 코드는 걷어낸다
            "thread-context": (
                f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요",
                "리마인더가 두 번 와요",
                [
                    _message("U0001", "어제 리마인더 두 번 왔는데 저만 그런가요?"),
                    _message("U0002", f"저도요 <@{ANNA_ID}>"),
                ],
                "### 슬랙 스레드\n\n> **U0001**: 어제 리마인더 두 번 왔는데 저만 그런가요?"
                "\n>\n> **U0002**: 저도요\n\n" + LINKED_FOOTER,
            ),
            "exact-body": (
                f"<@{ANNA_ID}> 새로운 이슈 제목\n요청 본문\n  코드",
                "제목",
                [_message("U1", "첫 대화"), _message("U2", f"다음 대화 <@{ANNA_ID}>")],
                "요청 본문\n  코드\n\n### 슬랙 스레드\n\n> **U1**: 첫 대화\n>\n> **U2**: 다음 대화"
                "\n\n" + LINKED_FOOTER,
            ),
        }.items():
            with self.subTest(case=name):
                sut = self._build_sut(text, in_thread=replies is not None)
                self.mock_slack_client.get_replies.return_value = replies
                assert sut.handle_mention() is True
                prefix = THREADED_LOOKUPS if replies is not None else CHANNEL_LOOKUPS
                assert self.calls.mock_calls == prefix + [
                    call.github.create_issue(title=title, body=body),
                    PUBLIC_REPLY,
                ]

    def test_lookup_outcomes_preserve_each_successful_result(self):
        for name, (thread_error, link_error, body, warnings) in {
            "success-success": (
                None,
                None,
                "본문\n\n### 슬랙 스레드\n\n> **U1**: 대화\n\n" + LINKED_FOOTER,
                [],
            ),
            "failure-success": (
                RuntimeError("스레드 실패 🐍"),
                None,
                "본문\n\n" + LINKED_FOOTER,
                [THREAD_WARNING],
            ),
            "success-failure": (
                None,
                GithubApiError("링크 실패 🧪"),
                "본문\n\n### 슬랙 스레드\n\n> **U1**: 대화\n\n" + FOOTER,
                [LINK_WARNING],
            ),
            "failure-failure": (
                RuntimeError("스레드 실패 🐍"),
                GithubApiError("링크 실패 🧪"),
                "본문\n\n" + FOOTER,
                [THREAD_WARNING, LINK_WARNING],
            ),
        }.items():
            with self.subTest(case=name):
                sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 제목\n본문", in_thread=True)
                self.mock_slack_client.get_replies.return_value = [_message("U1", "대화")]
                self.mock_slack_client.get_replies.side_effect = thread_error
                self.mock_slack_client.get_permalink.side_effect = link_error
                with self.assertLogs(
                    "features.issues.handlers.create_issue", level="INFO"
                ) as logs:
                    assert sut.handle_mention() is True
                assert logs.output == warnings + [SUCCESS_LOG]
                assert self.calls.mock_calls == THREADED_LOOKUPS + [
                    call.github.create_issue(title="제목", body=body),
                    PUBLIC_REPLY,
                ]

    def test_body_keeps_going_without_permalink(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요")
        self.mock_slack_client.get_permalink.return_value = None
        assert sut.handle_mention() is True
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
            call.github.create_issue(title="리마인더가 두 번 와요", body=FOOTER),
            PUBLIC_REPLY,
        ]

    def test_success_link_escaping_uses_github_title(self):
        for name, (text, title, issue, reply) in {
            "script": (
                f"<@{ANNA_ID}> 새로운 이슈 <script> 태그가 안 먹어요",
                "<script> 태그가 안 먹어요",
                Issue(
                    number=42,
                    title="<script> 태그가 안 먹어요",
                    url="https://github.com/AUSG/anna-v2/issues/42",
                ),
                "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/42|#42 &lt;script&gt; 태그가 안 먹어요>",
            ),
            "pipe-ampersand": (
                f"<@{ANNA_ID}> 새로운 이슈 제목",
                "제목",
                Issue(
                    number=7,
                    title="<script> | &lt; & > 🐍",
                    url="https://github.com/AUSG/anna-v2/issues/7",
                ),
                "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/7|#7 &lt;script&gt; &#124; &lt; & &gt; 🐍>",
            ),
        }.items():
            with self.subTest(case=name):
                sut = self._build_sut(text)
                self.mock_github_client.create_issue.return_value = issue
                assert sut.handle_mention() is True
                # 제목의 <, > 가 그대로 나가면 슬랙 링크 표기가 깨진다
                assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
                    call.github.create_issue(title=title, body=LINKED_FOOTER),
                    call.slack.send_message(msg=reply, ts="1689403771.805849"),
                ]

    def test_refusal_before_lookups(self):
        for name, (text, in_thread, enabled, expected) in {
            "usage-original": (f"<@{ANNA_ID}> 이슈 만들어줘", False, True, [USAGE_REPLY]),
            "usage-thread": (f"<@{ANNA_ID}> 새로운 이슈", True, True, [USAGE_REPLY]),
            "empty-first-line": (
                f"<@{ANNA_ID}> 새로운 이슈 ?\n본문만 있음",
                True,
                True,
                [USAGE_REPLY],
            ),
            "disabled-original": (
                f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요",
                False,
                False,
                [ENABLED, DISABLED_REPLY],
            ),
            "disabled-thread": (
                f"<@{ANNA_ID}> 새로운 이슈 제목",
                True,
                False,
                [ENABLED, DISABLED_REPLY],
            ),
        }.items():
            with self.subTest(case=name):
                sut = self._build_sut(text, in_thread=in_thread, enabled=enabled)
                assert sut.handle_mention() is False
                assert self.calls.mock_calls == expected

    def test_unmatched_command_does_not_call_any_client(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 이슈 파악해줘", in_thread=True)
        assert sut.handle_mention() is False
        assert self.calls.mock_calls == []

    def test_github_error_is_logged_and_private_after_lookups(self):
        for name, (text, title, in_thread, reason, reply) in {
            "connection": (
                f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요",
                "리마인더가 두 번 와요",
                False,
                "깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!",
                ":blob-fearful: 이슈를 만들지 못했어. 깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!",
            ),
            "special-reason": (
                f"<@{ANNA_ID}> 새로운 이슈 제목",
                "제목",
                True,
                "거절 <403>|🐍",
                ":blob-fearful: 이슈를 만들지 못했어. 거절 <403>|🐍",
            ),
        }.items():
            with self.subTest(case=name):
                sut = self._build_sut(text, in_thread=in_thread)
                self.mock_slack_client.get_replies.return_value = []
                self.mock_github_client.create_issue.side_effect = GithubApiError(
                    reason
                )
                with self.assertLogs(
                    "features.issues.handlers.create_issue", level="WARNING"
                ) as logs:
                    assert sut.handle_mention() is False
                assert logs.output == [
                    f"WARNING:features.issues.handlers.create_issue:Failed to create an issue for UQJ8HQJG5: {reason}"
                ]
                prefix = THREADED_LOOKUPS if in_thread else CHANNEL_LOOKUPS
                # 실패는 요청한 사람에게만 알린다 (스레드를 에러로 어지럽히지 않게)
                assert self.calls.mock_calls == prefix + [
                    call.github.create_issue(title=title, body=LINKED_FOOTER),
                    call.slack.send_message_only_visible_to_user(
                        msg=reply,
                        channel="C03SZTDEDK3",
                        ts="1689403771.805849",
                        user_id="UQJ8HQJG5",
                    ),
                ]

    def test_unexpected_creation_error_propagates_without_result_reply(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 제목")
        failure = ValueError("예상하지 않은 응답")
        self.mock_github_client.create_issue.side_effect = failure

        with self.assertRaises(ValueError) as error:
            sut.handle_mention()

        assert error.exception is failure
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
            call.github.create_issue(title="제목", body=LINKED_FOOTER)
        ]

    def test_success_reply_failure_does_not_recreate_or_become_private_error(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 제목")
        failure = GithubApiError("공개 안내 실패")
        self.mock_slack_client.send_message.side_effect = failure

        with self.assertRaises(GithubApiError) as error:
            sut.handle_mention()

        assert error.exception is failure
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
            call.github.create_issue(title="제목", body=LINKED_FOOTER),
            PUBLIC_REPLY,
        ]
        self.mock_slack_client.send_message_only_visible_to_user.assert_not_called()

    def test_creation_error_reply_failure_propagates_without_retry(self):
        sut = self._build_sut(f"<@{ANNA_ID}> 새로운 이슈 제목")
        self.mock_github_client.create_issue.side_effect = GithubApiError("생성 실패")
        failure = RuntimeError("비공개 안내 실패")
        self.mock_slack_client.send_message_only_visible_to_user.side_effect = failure

        with self.assertRaises(RuntimeError) as error:
            sut.handle_mention()

        assert error.exception is failure
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
            call.github.create_issue(title="제목", body=LINKED_FOOTER),
            call.slack.send_message_only_visible_to_user(
                msg=":blob-fearful: 이슈를 만들지 못했어. 생성 실패",
                channel=sut.channel,
                ts=sut.ts,
                user_id=sut.user,
            ),
        ]
        self.mock_slack_client.send_message.assert_not_called()

    def test_thread_context_cases(self):
        for name, (messages, expected) in {
            "inner-newlines": (
                [
                    SimpleNamespace(user="U0", text=None),
                    _message("U1", f" <@{ANNA_ID}> \n "),
                    _message("U2", " 첫 줄\r\n  코드\u2028끝  "),
                    _message("U3", " 🐍 "),
                ],
                "> **U2**: 첫 줄\r\n  코드\u2028끝\n>\n> **U3**: 🐍",
            ),
            "blank-without-user": ([SimpleNamespace(text=" ")], ""),
            "exact-budget": (
                [
                    _message("U0", "제외"),
                    _message("U1", "가" * 1489),
                    _message("U2", "나" * 1489),
                ],
                "> **U1**: " + "가" * 1489 + "\n>\n> **U2**: " + "나" * 1489,
            ),
            "one-over-budget": (
                [_message("U1", "가" * 1489), _message("U2", "나" * 1490)],
                "> **U2**: " + "나" * 1490,
            ),
            "latest-oversize": (
                [_message("U1", "이전 대화"), _message("U2", "🐍" * 3500)],
                "> **U2**: " + "🐍" * 3500,
            ),
            "stop-at-middle": (
                [
                    _message("U1", "짧은 과거"),
                    _message("U2", "가" * 3000),
                    _message("U3", "최신"),
                ],
                "> **U3**: 최신",
            ),
        }.items():
            with self.subTest(case=name):
                slack = MagicMock()
                slack.get_replies.return_value = messages
                sut = CreateIssue(_event(f"<@{ANNA_ID}> 새로운 이슈 제목", True), slack, None)
                assert sut._fetch_thread_context() == expected
                assert slack.mock_calls == [
                    call.get_replies(
                        channel="C03SZTDEDK3", thread_ts="1689403100.222939"
                    )
                ]
