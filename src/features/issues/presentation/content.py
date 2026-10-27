"""GitHub 이슈 본문과 슬랙 안내 문구."""

from typing import List, Optional

from features.issues.models import Issue
from shared.slack_models import Message
from shared.slack_commands import strip_mentions
from shared.text import strip_multiline

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
DISABLED_MESSAGE = "깃허브 토큰이 설정되지 않아서 이슈를 만들 수 없어. 운영진에게 알려줘!"


def build_issue_body(body: str, thread_context: str, footer: str) -> str:
    parts = []
    if body:
        parts.append(body)
    if thread_context:
        parts.append(f"### 슬랙 스레드\n\n{thread_context}")
    parts.append(footer)
    return "\n\n".join(parts)


def build_issue_footer(user: Optional[str], permalink: str) -> str:
    lines = ["---", f"슬랙에서 `{user}` 가 안나에게 요청해서 만들어진 이슈야."]
    if permalink:
        lines.append(f"원문: {permalink}")
    return "\n".join(lines)


def build_thread_context(messages: List[Message]) -> str:
    """스레드 대화를 인용문으로. 최근 메시지부터 채우고, 예산을 넘기는 오래된 메시지는 통째로 제외한다."""
    lines = []
    for m in messages:
        text = strip_mentions(m.text or "")
        if text:
            lines.append(f"> **{m.user}**: {text}")
    kept, total = [], 0
    for line in reversed(lines):
        if kept and total + len(line) + 1 > THREAD_CONTEXT_MAX_CHARS:
            break
        kept.append(line)
        total += len(line) + 1
    return "\n>\n".join(reversed(kept))


def _escape_link_text(text: str) -> str:
    """슬랙 링크 표기(`<url|텍스트>`) 안에서는 <, >, | 가 문법이라 제목에 있으면 링크가 깨진다."""
    return text.replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;")


def issue_created_message(issue: Issue) -> str:
    return f"이슈 만들었어! <{issue.url}|#{issue.number} {_escape_link_text(issue.title)}>"


def issue_failed_message(reason: str) -> str:
    return f":blob-fearful: 이슈를 만들지 못했어. {reason}"
