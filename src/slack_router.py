"""멘션 본문을 한 번 해석해 명령 값으로 바꾼다. 클라이언트 생성이나 API 호출은 없다.

우선순위: 명시적 질문(q)) > 명령 > 일반 질문 > 빈 멘션.
"""

from typing import Union

from features.bigchat.services.commands import (
    CreateBigchat,
    Reminder,
    is_create_bigchat,
    is_reminder,
    parse_create_bigchat,
    parse_reminder,
)
from features.bot_commands.models import Empty, Help, Shuffle, is_help, is_shuffle
from features.issues.models import CreateIssue
from features.issues.services.commands import is_create_issue, parse_issue_command
from features.questions.models import Question
from features.questions.services.commands import (
    is_explicit_question,
    parse_explicit_question,
    parse_plain_question,
)
from shared.slack_commands import SLACK_USER_PATTERN

MentionCommand = Union[
    Question, Shuffle, Reminder, CreateBigchat, CreateIssue, Help, Empty
]


def parse_mention(text: str, anna_id: str) -> MentionCommand:
    if is_explicit_question(text):
        return parse_explicit_question(text)
    if is_shuffle(text):
        # 섞을 대상에서 안나 자신은 뺀다
        return Shuffle(
            tuple(u for u in SLACK_USER_PATTERN.findall(text) if u != anna_id)
        )
    if is_reminder(text):
        return parse_reminder(text, anna_id)
    if is_create_bigchat(text):
        return parse_create_bigchat(text)
    if is_create_issue(text):
        return parse_issue_command(text)
    if is_help(text):
        return Help()
    question = parse_plain_question(text)
    return question if question else Empty()
