import logging
from typing import List, Optional

import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)

GITHUB_API_BASE_URL = "https://api.github.com"
# 응답 형식을 고정한다 (GitHub 은 버전 헤더가 없으면 계정 기본값을 쓴다)
GITHUB_API_VERSION = "2022-11-28"


class GithubApiError(Exception):
    """GitHub API 호출이 실패했을 때. reason 은 그대로 슬랙에 보여줄 수 있는 한국어 문장이다."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class Issue(BaseModel):
    number: int
    title: str
    url: str


class GithubClient:
    """안나 자신의 레포(기본값 AUSG/anna-v2)에 이슈를 만드는 클라이언트.

    토큰은 이슈를 만들 수 있는 최소 권한(Issues: Read and write)만 있으면 된다.
    토큰이 비어 있으면 is_enabled() 가 False 라서, 호출부는 기능을 꺼둔 것으로 취급하면 된다.
    """

    def __init__(self, token: str, repo: str, timeout: int = 10):
        self.token = token
        self.repo = repo.strip().strip("/")
        self.timeout = timeout

    def is_enabled(self) -> bool:
        return bool(self.token and self.repo)

    def create_issue(
        self, title: str, body: str = "", labels: Optional[List[str]] = None
    ) -> Issue:
        if not self.is_enabled():
            raise GithubApiError("깃허브 토큰이나 레포 설정이 비어 있어. 운영진에게 알려줘!")

        payload = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels

        try:
            resp = requests.post(
                f"{GITHUB_API_BASE_URL}/repos/{self.repo}/issues",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                },
                timeout=self.timeout,
            )
        except requests.exceptions.RequestException as ex:
            logger.warning("GitHub issue creation failed to reach the API: %s", ex)
            raise GithubApiError("깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!") from ex

        if resp.status_code != 201:
            logger.warning(
                "GitHub issue creation failed: status=%s, body=%s",
                resp.status_code,
                resp.text[:500],
            )
            raise GithubApiError(self._error_reason(resp.status_code))

        data = resp.json()
        return Issue(number=data["number"], title=data["title"], url=data["html_url"])

    def _error_reason(self, status_code: int) -> str:
        if status_code in (401, 403):
            return f"깃허브가 내 토큰을 거절했어 (HTTP {status_code}). 토큰 권한을 확인해줘!"
        if status_code == 404:
            # 이슈 권한이 없는 토큰도 404 를 준다 (레포 존재 여부를 숨기려는 GitHub 의 동작)
            return f"`{self.repo}` 레포를 찾지 못했어. 레포 이름이나 토큰 권한을 확인해줘!"
        if status_code == 410:
            return f"`{self.repo}` 레포의 이슈 기능이 꺼져 있어."
        if status_code == 422:
            return "깃허브가 이슈 내용을 거절했어. 제목이 너무 길거나 형식이 안 맞을 수 있어."
        return f"깃허브가 에러를 줬어 (HTTP {status_code}). 잠시 뒤에 다시 시도해줘!"
