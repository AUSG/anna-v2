import logging

from features.issues.presentation.content import (
    build_issue_body,
    build_issue_footer,
    parse_issue_command,
)
from shared.mention_handler import MentionHandler
from slack_router import MENTION_PATTERN as MENTION_PAT, matches_mention
from integrations.github import GithubApiError
from shared.utils import strip_multiline

logger = logging.getLogger(__name__)

# 스레드 맥락 과다 방지: 가장 최근부터 이 글자 수까지만 이슈 본문에 옮긴다
THREAD_CONTEXT_MAX_CHARS = 3000

USAGE = strip_multiline(
    """
    내 레포에 이슈를 만들어줄게. 제목을 같이 적어줘!
    - `새로운 이슈 <제목>`: 제목만으로 이슈를 만들어
    - 둘째 줄부터 쓴 내용은 이슈 본문이 돼
    - 스레드 안에서 부르면 그 스레드 대화도 본문에 같이 넣어둘게
    예) `새로운 이슈 빅챗 리마인더가 두 번 와요`"""
)


def _escape_link_text(text: str) -> str:
    """슬랙 링크 표기(`<url|텍스트>`) 안에서는 <, >, | 가 문법이라 제목에 있으면 링크가 깨진다."""
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;")


class CreateIssue(MentionHandler):
    """멘션 한 줄로 안나 자신의 레포(AUSG/anna-v2)에 이슈를 만드는 명령.

    슬랙에서 "이거 버그다" 하고 흘러가버리는 이야기를 그 자리에서 이슈로 남기는 게 목적이라,
    제목만 있으면 바로 만든다. 어디서 나온 이야기인지 추적할 수 있게 본문 끝에 원문
    permalink 를 붙인다.
    """

    def __init__(self, event, slack_client, github_client):
        self.text = event["text"]
        self.ts = event["ts"]
        self.channel = event.get("channel")
        # 스레드 안에서 멘션된 경우에만 thread_ts 가 존재
        self.thread_ts = event.get("thread_ts")
        self.user = event.get("user")
        self.slack_client = slack_client
        self.github_client = github_client

    def can_handle(self):
        return matches_mention("create_issue", self.text)

    def handle_mention(self):
        if not self.can_handle():
            return False

        title, body = parse_issue_command(self.text)
        if not title:
            self._reply_only_to_requester(USAGE)
            return False

        if not self.github_client.is_enabled():
            self._reply_only_to_requester("깃허브 토큰이 설정되지 않아서 이슈를 만들 수 없어. 운영진에게 알려줘!")
            return False

        try:
            issue = self.github_client.create_issue(
                title=title, body=self._build_body(body)
            )
        except GithubApiError as ex:
            logger.warning("Failed to create an issue for %s: %s", self.user, ex.reason)
            self._reply_only_to_requester(f":blob-fearful: 이슈를 만들지 못했어. {ex.reason}")
            return False

        logger.info("Issue #%d created by %s: %s", issue.number, self.user, issue.title)
        self.slack_client.send_message(
            msg=f"이슈 만들었어! <{issue.url}|#{issue.number} {_escape_link_text(issue.title)}>",
            ts=self.ts,
        )
        return True

    def _build_body(self, body: str) -> str:
        thread_context = self._fetch_thread_context()
        footer = build_issue_footer(self.user, self._permalink())
        return build_issue_body(body, thread_context, footer)

    def _permalink(self):
        if not self.channel or not self.ts:
            return ""
        try:
            return self.slack_client.get_permalink(self.channel, self.ts) or ""
        except Exception as ex:  # noqa: BLE001
            # permalink 는 부가 정보다 — 못 가져와도 이슈 생성 자체를 막지 않는다
            logger.warning("Failed to get permalink for the issue body: %s", ex)
            return ""

    def _fetch_thread_context(self) -> str:
        """스레드 안에서 부른 경우, 그 스레드 대화를 인용문으로 옮긴다."""
        if not self.channel or not self.thread_ts:
            return ""
        try:
            messages = self.slack_client.get_replies(
                channel=self.channel, thread_ts=self.thread_ts
            )
        except Exception as ex:  # noqa: BLE001
            logger.warning("Failed to fetch thread context for the issue body: %s", ex)
            return ""

        lines = []
        for m in messages:
            text = MENTION_PAT.sub("", m.text or "").strip()
            if text:
                lines.append(f"> **{m.user}**: {text}")

        # 최근 메시지부터 채우고, 예산을 넘기는 오래된 메시지는 통째로 제외 (메시지 중간이 끊기지 않게)
        kept, total = [], 0
        for line in reversed(lines):
            if kept and total + len(line) + 1 > THREAD_CONTEXT_MAX_CHARS:
                break
            kept.append(line)
            total += len(line) + 1
        return "\n>\n".join(reversed(kept))

    def _reply_only_to_requester(self, msg: str):
        self.slack_client.send_message_only_visible_to_user(
            msg=msg, channel=self.channel, ts=self.ts, user_id=self.user
        )
