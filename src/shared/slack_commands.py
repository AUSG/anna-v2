"""Slack 명령이 공통으로 사용하는 문법과 핸들러 계약."""

import re
from abc import ABC

MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")


class MentionHandler(ABC):
    def handle_mention(self):
        pass

    def can_handle(self):
        pass
