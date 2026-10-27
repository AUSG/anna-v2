"""네트워크 없이 앱 진입점을 연결하고 호출하기 위한 작은 런타임 대역."""

from types import SimpleNamespace
from unittest.mock import MagicMock


class FakeBoltApp:
    def __init__(self):
        self.handlers = {}

    def _register(self, kind, selector):
        def decorator(handler):
            self.handlers[kind, selector] = handler
            return handler

        return decorator

    def event(self, selector):
        return self._register("event", selector)

    def action(self, selector):
        return self._register("action", selector)

    def shortcut(self, selector):
        return self._register("shortcut", selector)

    def view(self, selector):
        return self._register("view", selector)


def fake_dependencies():
    return MagicMock(
        envs=SimpleNamespace(
            ICS_TOKEN_SECRET="testsecret",
            PUBLIC_BASE_URL="https://anna.test",
            SLACK_BOT_TOKEN="test-token",
            SLACK_SIGNING_SECRET="test-signing-secret",
            BIGCHAT_REMINDER_ENABLED=False,
            DAILY_DIGEST_ENABLED=False,
            DAILY_DIGEST_CHANNEL_ID="C_DIGEST",
            ADMIN_CHANNEL="C_ADMIN",
            ANNA_ID="UANNA",
            JOIN_BIGCHAT_EMOJI="gogo",
        )
    )
