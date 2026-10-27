"""네트워크 없이 앱 진입점을 연결하고 호출하기 위한 런타임 대역.

FakeRuntime 은 src/runtime.py 의 Runtime 계약을 그대로 따른다. 외부 세계는 전부
Protocol 을 spec 으로 삼은 MagicMock 이라, 계약에 없는 메서드를 부르면 바로 실패한다.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from features.issues.ports import GithubGateway
from features.members.ports import MemberDirectory
from features.questions.ports import QAGateway
from shared.gateways import SheetsGateway, SlackGateway


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


def fake_settings(**overrides):
    values = dict(
        ICS_TOKEN_SECRET="testsecret",
        PUBLIC_BASE_URL="https://anna.test",
        SLACK_BOT_TOKEN="test-token",
        SLACK_SIGNING_SECRET="test-signing-secret",
        BIGCHAT_REMINDER_ENABLED=False,
        DAILY_DIGEST_ENABLED=False,
        DAILY_DIGEST_CHANNEL_ID="C_DIGEST",
        ADMIN_CHANNEL="C_ADMIN",
        FREETALK_CHANNEL_ID="C_FREETALK",
        AUTO_REPLY_CHANNEL_ID="C03SZTDEDK3",
        ANNA_ID="UANNA",
        JOIN_BIGCHAT_EMOJI="gogo",
        GITHUB_TOKEN="ghp_test",
        GITHUB_REPO="AUSG/anna-v2",
        QA_SERVER_BASE_URL="http://qa.test",
        QA_API_KEY="qa-key",
        MEMBERS_INFO_WORKSHEET_ID=7,
        LOGLEVEL="DEBUG",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def fake_slack() -> MagicMock:
    slack = MagicMock(spec=SlackGateway)
    slack.get_thread.return_value = []
    slack.get_thread_of_message.return_value = []
    slack.get_reaction.return_value = None
    slack.get_permalink.return_value = None
    slack.download_file.return_value = None
    return slack


class FakeRuntime:
    """slack_client() 는 어떤 WebClient 를 받아도 같은 slack 대역을 돌려준다."""

    def __init__(self, settings=None):
        self.settings = settings or fake_settings()
        self.slack = fake_slack()
        self._sheets = MagicMock(spec=SheetsGateway)
        self._members = MagicMock(spec=MemberDirectory)
        self._members.find.return_value = None
        self._members.email_to_slack_ids.return_value = {}
        self._qa = MagicMock(spec=QAGateway)
        self._github = MagicMock(spec=GithubGateway)
        self._github.is_enabled.return_value = True
        self.web_clients = []

    def slack_client(self, web_client):
        return self.slack

    def web_client(self):
        client = MagicMock(name="WebClient")
        self.web_clients.append(client)
        return client

    def sheets(self):
        return self._sheets

    def members(self):
        return self._members

    def qa(self):
        return self._qa

    def github(self):
        return self._github


def fake_runtime(**settings_overrides) -> FakeRuntime:
    return FakeRuntime(fake_settings(**settings_overrides))
