"""Slack 명령 문법에서 공통으로 쓰는 패턴."""

import re

MENTION_PATTERN = re.compile(r"<@[A-Z0-9]+>")
SLACK_USER_PATTERN = re.compile(r"<@([A-Z0-9]+)>")


def strip_mentions(text: str) -> str:
    return MENTION_PATTERN.sub("", text).strip()
