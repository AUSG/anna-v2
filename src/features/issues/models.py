"""이슈 생성 명령의 값과 결과."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CreateIssue:
    title: str
    body: str = ""


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    url: str


@dataclass(frozen=True)
class IssueCreationFailed:
    """reason 은 그대로 슬랙에 보여줄 수 있는 한국어 문장이다."""

    reason: str
