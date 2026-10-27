"""멘션 한 줄로 안나 자신의 레포(AUSG/anna-v2)에 이슈를 만드는 명령.

슬랙에서 "이거 버그다" 하고 흘러가버리는 이야기를 그 자리에서 이슈로 남기는 게 목적이라,
제목만 있으면 바로 만든다. 어디서 나온 이야기인지 추적할 수 있게 본문 끝에 원문
permalink 를 붙인다.
"""

import logging

from features.issues.models import CreateIssue, IssueCreationFailed
from features.issues.ports import GithubGateway
from features.issues.presentation.content import (
    DISABLED_MESSAGE,
    USAGE,
    build_issue_body,
    build_issue_footer,
    build_thread_context,
    issue_created_message,
    issue_failed_message,
)
from shared.gateways import SlackGateway
from shared.slack_events import MentionEvent

logger = logging.getLogger(__name__)


def create_issue(
    command: CreateIssue,
    event: MentionEvent,
    slack: SlackGateway,
    github: GithubGateway,
) -> bool:
    def reply_only_to_requester(text: str):
        slack.send_ephemeral(event.channel, event.user, text, ts=event.ts)

    if not command.title:
        reply_only_to_requester(USAGE)
        return False
    if not github.is_enabled():
        reply_only_to_requester(DISABLED_MESSAGE)
        return False

    body = build_issue_body(
        command.body,
        _thread_context(event, slack),
        build_issue_footer(event.user, _permalink(event, slack)),
    )
    issue = github.create_issue(title=command.title, body=body)
    if isinstance(issue, IssueCreationFailed):
        logger.warning("Failed to create an issue for %s: %s", event.user, issue.reason)
        reply_only_to_requester(issue_failed_message(issue.reason))
        return False

    logger.info("Issue #%d created by %s: %s", issue.number, event.user, issue.title)
    slack.send_thread_message(event.channel, event.ts, issue_created_message(issue))
    return True


def _permalink(event: MentionEvent, slack: SlackGateway) -> str:
    try:
        return slack.get_permalink(event.channel, event.ts) or ""
    except Exception as ex:
        # permalink 는 부가 정보다. 못 가져와도 이슈 생성 자체를 막지 않는다
        logger.warning("Failed to get permalink for the issue body: %s", ex)
        return ""


def _thread_context(event: MentionEvent, slack: SlackGateway) -> str:
    """스레드 안에서 부른 경우에만 그 스레드 대화를 옮긴다."""
    if not event.thread_ts:
        return ""
    try:
        messages = slack.get_thread(event.channel, event.thread_ts)
    except Exception as ex:
        logger.warning("Failed to fetch thread context for the issue body: %s", ex)
        return ""
    return build_thread_context(messages)
