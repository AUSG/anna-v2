"""대화 선택의 기존 import 경로를 유지한다."""

from features.questions.models import (
    MAX_CONVERSATION_CHARS as MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGES as MAX_CONVERSATION_MESSAGES,
    select_conversation as select_conversation,
)
