"""기능이 실행 환경에 요구하는 계약. 구현은 bootstrap 이, 테스트는 대역이 제공한다.

features 는 이 모듈과 shared/gateways 의 Protocol 만 보고, bootstrap 을 역으로 import 하지 않는다.
"""

from typing import Protocol

from slack_sdk import WebClient

from config.env_config import Settings
from features.issues.ports import GithubGateway
from features.members.ports import MemberDirectory
from features.questions.ports import QAGateway
from shared.gateways import SheetsGateway, SlackGateway


class Runtime(Protocol):
    settings: Settings

    def slack_client(self, web_client: WebClient) -> SlackGateway:
        """Bolt 가 넘겨준 client 나 web_client() 로 만든 클라이언트를 감싼다."""
        ...

    def web_client(self) -> WebClient:
        """이벤트 컨텍스트 밖(스케줄 잡, HTTP)에서 쓸 WebClient."""
        ...

    def sheets(self) -> SheetsGateway:
        ...

    def members(self) -> MemberDirectory:
        ...

    def qa(self) -> QAGateway:
        ...

    def github(self) -> GithubGateway:
        ...
