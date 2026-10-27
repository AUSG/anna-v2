from typing import Protocol, Union

from features.issues.models import Issue, IssueCreationFailed


class GithubGateway(Protocol):
    def is_enabled(self) -> bool:
        ...

    def create_issue(
        self, title: str, body: str = ""
    ) -> Union[Issue, IssueCreationFailed]:
        ...
