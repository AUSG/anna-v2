import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, call

from features.issues.models import CreateIssue, Issue, IssueCreationFailed
from features.issues.ports import GithubGateway
from features.issues.presentation.content import DISABLED_MESSAGE, USAGE
from features.issues.slack import create_issue
from shared.slack_events import MentionEvent
from shared.slack_models import Message
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import create_sample_app_mention_event

ANNA_ID = "U01BN035Y6L"
CHANNEL = "C03SZTDEDK3"
TS = "1689403771.805849"
THREAD_TS = "1689403100.222939"
USER = "UQJ8HQJG5"
FOOTER = "---\n슬랙에서 `UQJ8HQJG5` 가 안나에게 요청해서 만들어진 이슈야."
LINKED_FOOTER = (
    FOOTER + "\n원문: https://ausg.slack.com/archives/C03SZTDEDK3/p1689403771805849"
)
ENABLED = call.github.is_enabled()
THREAD = call.slack.get_thread(CHANNEL, THREAD_TS)
PERMALINK = call.slack.get_permalink(CHANNEL, TS)
CHANNEL_LOOKUPS = [ENABLED, PERMALINK]
THREADED_LOOKUPS = [ENABLED, THREAD, PERMALINK]
CREATE_TITLE = call.github.create_issue(title="제목", body=LINKED_FOOTER)
# 이슈 링크를 스레드에 공개로 알려서, 만들어진 걸 다 같이 볼 수 있게 한다
PUBLIC_REPLY = call.slack.send_thread_message(
    CHANNEL,
    TS,
    "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/42|#42 빅챗 리마인더가 두 번 와요>",
)
USAGE_REPLY = call.slack.send_ephemeral(CHANNEL, USER, USAGE, ts=TS)
DISABLED_REPLY = call.slack.send_ephemeral(CHANNEL, USER, DISABLED_MESSAGE, ts=TS)
SUCCESS_LOG = (
    "INFO:features.issues.slack:Issue #42 created by UQJ8HQJG5: 빅챗 리마인더가 두 번 와요"
)
THREAD_WARNING = (
    "WARNING:features.issues.slack:Failed to fetch thread context for the issue body: "
    "스레드 실패 🐍"
)
LINK_WARNING = (
    "WARNING:features.issues.slack:Failed to get permalink for the issue body: 링크 실패 🧪"
)


def _event(in_thread=False):
    payload = create_sample_app_mention_event(f"<@{ANNA_ID}> 새로운 이슈 제목")
    if not in_thread:
        # 스레드 밖(채널 최상단)에서의 멘션에는 thread_ts 가 없다
        del payload["thread_ts"]
    return MentionEvent.from_payload(payload)


def _private_reply(text):
    return call.slack.send_ephemeral(CHANNEL, USER, text, ts=TS)


def _message(user, text):
    return Message(
        ts=THREAD_TS, thread_ts=THREAD_TS, channel=CHANNEL, user=user, text=text
    )


class CreateIssueTestBase(unittest.TestCase):
    def setUp(self):
        self.slack = fake_slack()
        self.slack.get_permalink.return_value = (
            "https://ausg.slack.com/archives/C03SZTDEDK3/p1689403771805849"
        )
        self.github = MagicMock(spec=GithubGateway)
        self.github.is_enabled.return_value = True
        self.github.create_issue.return_value = Issue(
            number=42,
            title="빅챗 리마인더가 두 번 와요",
            url="https://github.com/AUSG/anna-v2/issues/42",
        )
        self.calls = MagicMock()
        self.calls.attach_mock(self.slack, "slack")
        self.calls.attach_mock(self.github, "github")

    def _run(self, command, in_thread=False):
        return create_issue(command, _event(in_thread), self.slack, self.github)


class TestCreateIssue(CreateIssueTestBase):
    def test_exact_body_and_success_call_order(self):
        for name, (command, replies, body) in {
            "title-only": (
                CreateIssue("빅챗 리마인더가 두 번 와요"),
                None,
                LINKED_FOOTER,
            ),
            "lf-body": (
                CreateIssue("리마인더가 두 번 와요", "어제 저녁에 DM 이 두 통 왔어.\n재현 100%"),
                None,
                "어제 저녁에 DM 이 두 통 왔어.\n재현 100%\n\n" + LINKED_FOOTER,
            ),
            # 스레드 인용에서도 멘션 코드는 걷어낸다
            "thread-context": (
                CreateIssue("리마인더가 두 번 와요"),
                [
                    _message("U0001", "어제 리마인더 두 번 왔는데 저만 그런가요?"),
                    _message("U0002", f"저도요 <@{ANNA_ID}>"),
                ],
                "### 슬랙 스레드\n\n> **U0001**: 어제 리마인더 두 번 왔는데 저만 그런가요?"
                "\n>\n> **U0002**: 저도요\n\n" + LINKED_FOOTER,
            ),
            "exact-body": (
                CreateIssue("제목", "요청 본문\n  코드"),
                [_message("U1", "첫 대화"), _message("U2", f"다음 대화 <@{ANNA_ID}>")],
                "요청 본문\n  코드\n\n### 슬랙 스레드\n\n> **U1**: 첫 대화\n>\n> **U2**: 다음 대화"
                "\n\n" + LINKED_FOOTER,
            ),
            "empty-thread": (CreateIssue("제목"), [], LINKED_FOOTER),
        }.items():
            with self.subTest(case=name):
                self.setUp()
                self.slack.get_thread.return_value = replies
                assert self._run(command, in_thread=replies is not None) is True
                prefix = THREADED_LOOKUPS if replies is not None else CHANNEL_LOOKUPS
                assert self.calls.mock_calls == prefix + [
                    call.github.create_issue(title=command.title, body=body),
                    PUBLIC_REPLY,
                ]

    def test_thread_is_read_only_when_mentioned_inside_a_thread(self):
        assert self._run(CreateIssue("제목")) is True
        self.slack.get_thread.assert_not_called()
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [CREATE_TITLE, PUBLIC_REPLY]

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
                RuntimeError("링크 실패 🧪"),
                "본문\n\n### 슬랙 스레드\n\n> **U1**: 대화\n\n" + FOOTER,
                [LINK_WARNING],
            ),
            "failure-failure": (
                RuntimeError("스레드 실패 🐍"),
                RuntimeError("링크 실패 🧪"),
                "본문\n\n" + FOOTER,
                [THREAD_WARNING, LINK_WARNING],
            ),
        }.items():
            with self.subTest(case=name):
                self.setUp()
                self.slack.get_thread.return_value = [_message("U1", "대화")]
                self.slack.get_thread.side_effect = thread_error
                self.slack.get_permalink.side_effect = link_error
                with self.assertLogs("features.issues.slack", level="INFO") as logs:
                    assert self._run(CreateIssue("제목", "본문"), in_thread=True) is True
                assert logs.output == warnings + [SUCCESS_LOG]
                assert self.calls.mock_calls == THREADED_LOOKUPS + [
                    call.github.create_issue(title="제목", body=body),
                    PUBLIC_REPLY,
                ]

    def test_keeps_going_when_thread_context_fails(self):
        self.slack.get_thread.side_effect = Exception("boom")
        with self.assertLogs("features.issues.slack", level="WARNING") as logs:
            assert self._run(CreateIssue("리마인더가 두 번 와요"), in_thread=True) is True
        assert logs.output == [
            "WARNING:features.issues.slack:Failed to fetch thread context for the issue body: boom"
        ]
        assert self.calls.mock_calls == THREADED_LOOKUPS + [
            call.github.create_issue(title="리마인더가 두 번 와요", body=LINKED_FOOTER),
            PUBLIC_REPLY,
        ]

    def test_body_keeps_going_without_permalink(self):
        for permalink in (None, ""):
            with self.subTest(permalink=permalink):
                self.setUp()
                self.slack.get_permalink.return_value = permalink
                assert self._run(CreateIssue("리마인더가 두 번 와요")) is True
                assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
                    call.github.create_issue(title="리마인더가 두 번 와요", body=FOOTER),
                    PUBLIC_REPLY,
                ]

    def test_success_link_escaping_uses_github_title(self):
        for name, (title, issue, reply) in {
            "script": (
                "<script> 태그가 안 먹어요",
                Issue(
                    number=42,
                    title="<script> 태그가 안 먹어요",
                    url="https://github.com/AUSG/anna-v2/issues/42",
                ),
                "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/42|#42 &lt;script&gt; 태그가 안 먹어요>",
            ),
            "pipe-ampersand": (
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
                self.setUp()
                self.github.create_issue.return_value = issue
                assert self._run(CreateIssue(title)) is True
                # 제목의 <, > 가 그대로 나가면 슬랙 링크 표기가 깨진다
                assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
                    call.github.create_issue(title=title, body=LINKED_FOOTER),
                    call.slack.send_thread_message(CHANNEL, TS, reply),
                ]

    def test_refusal_before_lookups(self):
        for name, (command, in_thread, enabled, expected) in {
            "usage-original": (CreateIssue(""), False, True, [USAGE_REPLY]),
            "usage-thread": (CreateIssue(""), True, True, [USAGE_REPLY]),
            "empty-first-line": (
                CreateIssue("", "본문만 있음"),
                True,
                True,
                [USAGE_REPLY],
            ),
            "disabled-original": (
                CreateIssue("리마인더가 두 번 와요"),
                False,
                False,
                [ENABLED, DISABLED_REPLY],
            ),
            "disabled-thread": (
                CreateIssue("제목"),
                True,
                False,
                [ENABLED, DISABLED_REPLY],
            ),
        }.items():
            with self.subTest(case=name):
                self.setUp()
                self.github.is_enabled.return_value = enabled
                assert self._run(command, in_thread=in_thread) is False
                assert self.calls.mock_calls == expected

    def test_github_failure_is_logged_and_private_after_lookups(self):
        for name, (title, in_thread, reason, reply) in {
            "connection": (
                "리마인더가 두 번 와요",
                False,
                "깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!",
                ":blob-fearful: 이슈를 만들지 못했어. 깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!",
            ),
            "special-reason": (
                "제목",
                True,
                "거절 <403>|🐍",
                ":blob-fearful: 이슈를 만들지 못했어. 거절 <403>|🐍",
            ),
        }.items():
            with self.subTest(case=name):
                self.setUp()
                self.github.create_issue.return_value = IssueCreationFailed(reason)
                with self.assertLogs("features.issues.slack", level="WARNING") as logs:
                    assert self._run(CreateIssue(title), in_thread=in_thread) is False
                assert logs.output == [
                    f"WARNING:features.issues.slack:Failed to create an issue for UQJ8HQJG5: {reason}"
                ]
                prefix = THREADED_LOOKUPS if in_thread else CHANNEL_LOOKUPS
                # 실패는 요청한 사람에게만 알린다 (스레드를 에러로 어지럽히지 않게)
                assert self.calls.mock_calls == prefix + [
                    call.github.create_issue(title=title, body=LINKED_FOOTER),
                    _private_reply(reply),
                ]

    def test_exception_propagation_by_stage(self):
        for stage, (command, in_thread, target, error, prefix) in {
            "create_issue": (
                CreateIssue("제목"),
                False,
                "github",
                ValueError("예상하지 않은 응답"),
                CHANNEL_LOOKUPS + [CREATE_TITLE],
            ),
            "is_enabled": (
                CreateIssue("제목"),
                True,
                "github",
                RuntimeError("활성화 검사 실패"),
                [ENABLED],
            ),
            "send_ephemeral": (
                CreateIssue(""),
                True,
                "slack",
                RuntimeError("비공개 안내 실패"),
                [USAGE_REPLY],
            ),
        }.items():
            with self.subTest(stage=stage):
                self.setUp()
                getattr(getattr(self, target), stage).side_effect = error
                with self.assertRaises(type(error)) as caught:
                    self._run(command, in_thread=in_thread)
                assert caught.exception is error
                assert self.calls.mock_calls == prefix

    def test_success_reply_failure_does_not_undo_creation_or_become_private_error(self):
        error = RuntimeError("공개 안내 실패")
        self.slack.send_thread_message.side_effect = error
        with self.assertLogs("features.issues.slack", level="INFO") as logs:
            with self.assertRaises(RuntimeError) as caught:
                self._run(CreateIssue("제목"))
        assert caught.exception is error
        assert logs.output == [SUCCESS_LOG]
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [CREATE_TITLE, PUBLIC_REPLY]

    def test_github_failure_reply_exception_is_not_caught_again(self):
        self.github.create_issue.return_value = IssueCreationFailed("생성 실패")
        error = RuntimeError("비공개 안내 실패")
        self.slack.send_ephemeral.side_effect = error
        with self.assertRaises(RuntimeError) as caught:
            self._run(CreateIssue("제목"))
        assert caught.exception is error
        assert self.calls.mock_calls == CHANNEL_LOOKUPS + [
            CREATE_TITLE,
            _private_reply(":blob-fearful: 이슈를 만들지 못했어. 생성 실패"),
        ]

    def test_invalid_thread_result_propagates(self):
        for name, (messages, error) in {
            "missing-user": ([SimpleNamespace(text="대화")], AttributeError),
            "none-result": (None, TypeError),
        }.items():
            with self.subTest(case=name):
                self.setUp()
                self.slack.get_thread.return_value = messages
                with self.assertRaises(error):
                    self._run(CreateIssue("제목"), in_thread=True)
                assert self.calls.mock_calls == [ENABLED, THREAD]

    def test_lookup_does_not_swallow_base_exception(self):
        for method in ("get_thread", "get_permalink"):
            with self.subTest(method=method):
                self.setUp()
                error = KeyboardInterrupt("중단")
                getattr(self.slack, method).side_effect = error
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self._run(CreateIssue("제목"), in_thread=True)
                assert caught.exception is error
                assert self.calls.mock_calls == (
                    [ENABLED, THREAD] if method == "get_thread" else THREADED_LOOKUPS
                )
