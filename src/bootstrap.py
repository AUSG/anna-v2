"""의존성 조립. 전역 설정을 읽는 유일한 곳이다."""

from dataclasses import dataclass, field
from functools import cached_property

from slack_sdk import WebClient

from config.env_config import Settings
from features.issues.ports import GithubGateway
from features.members.ports import MemberDirectory
from features.members.services.directory import MemberManager
from features.questions.ports import QAGateway
from integrations.github import GithubClient
from integrations.google_sheets import GoogleSpreadsheetClient
from integrations.qa import QAClient
from integrations.slack import SlackClient
from shared.gateways import SheetsGateway, SlackGateway


@dataclass
class ProductionRuntime:
    """외부 클라이언트는 처음 쓰일 때 만들고 프로세스 안에서 공유한다."""

    settings: Settings = field(default_factory=Settings)

    def slack_client(self, web_client: WebClient) -> SlackGateway:
        return SlackClient(web_client)

    def web_client(self) -> WebClient:
        return WebClient(token=self.settings.SLACK_BOT_TOKEN)

    @cached_property
    def _sheets(self) -> SheetsGateway:
        return GoogleSpreadsheetClient(self.settings)

    def sheets(self) -> SheetsGateway:
        return self._sheets

    @cached_property
    def _members(self) -> MemberDirectory:
        return MemberManager(self.sheets(), self.settings.MEMBERS_INFO_WORKSHEET_ID)

    def members(self) -> MemberDirectory:
        return self._members

    @cached_property
    def _qa(self) -> QAGateway:
        return QAClient(
            qa_server_base_url=self.settings.QA_SERVER_BASE_URL,
            api_key=self.settings.QA_API_KEY,
        )

    def qa(self) -> QAGateway:
        return self._qa

    def github(self) -> GithubGateway:
        return GithubClient(self.settings.GITHUB_TOKEN, self.settings.GITHUB_REPO)


def create_runtime(settings: Settings = None) -> ProductionRuntime:
    return ProductionRuntime(settings=settings or Settings())
