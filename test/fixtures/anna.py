"""main 과 동일한 진입점을 외부 API·스케줄러 실행 없이 로딩한다."""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import slack_bolt

from config import env_config, log_config
from shared import scheduling


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
    monkeypatch.setattr(slack_bolt, "App", MagicMock(return_value=bolt_app))
    monkeypatch.setattr(log_config, "init_logger", MagicMock())
    scheduler = MagicMock()
    monkeypatch.setattr(scheduling, "DailyScheduler", scheduler)
    path = Path(__file__).resolve().parents[2] / "src/anna.py"
    spec = importlib.util.spec_from_file_location("anna_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, bolt_app, scheduler
