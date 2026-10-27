"""앱 factory를 외부 API·스케줄러 실행 없이 조립한다."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import anna
from config import env_config


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


def load_anna(monkeypatch, *, bolt_app=None, reminders=False, digest=False):
    settings = {
        "SLACK_BOT_TOKEN": "xoxb-test",
        "SLACK_SIGNING_SECRET": "test-signing-secret",
        "ANNA_ID": "U01BN035Y6L",
        "ADMIN_CHANNEL": "C_ADMIN",
        "JOIN_BIGCHAT_EMOJI": "gogo",
        "ICS_TOKEN_SECRET": "testsecret",
        "PUBLIC_BASE_URL": "https://anna.test",
        "BIGCHAT_REMINDER_ENABLED": reminders,
        "DAILY_DIGEST_ENABLED": digest,
    }
    for name, value in settings.items():
        monkeypatch.setattr(env_config.envs, name, value)
    bolt_app = bolt_app if bolt_app is not None else FakeBoltApp()
    monkeypatch.setattr(anna, "init_logger", MagicMock())
    scheduler = MagicMock()
    monkeypatch.setattr(anna, "DailyScheduler", scheduler)
    app = anna.create_app(env_config.envs, bolt_app=bolt_app)
    runtime = SimpleNamespace(
        flask_app=app,
        settings=env_config.envs,
        services=app.extensions["anna_services"],
    )
    return runtime, bolt_app, scheduler
