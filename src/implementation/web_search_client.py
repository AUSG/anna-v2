import logging
from dataclasses import dataclass
from typing import Any, List
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

# 검색 결과 하나당 본문 미리보기 길이. LLM 컨텍스트에 그대로 들어가므로 짧게 유지한다
MAX_RESULT_CONTENT_CHARS = 600
MAX_RESULT_TITLE_CHARS = 200


@dataclass
class WebSearchResult:
    """A single web search hit."""

    title: str
    url: str
    content: str
    published_date: str = ""


class WebSearchClient:
    """Tavily 웹 검색 (https://docs.tavily.com). 실패하면 빈 리스트를 돌려주고 로그만 남긴다.

    질답은 웹 검색 없이도 동작해야 하므로, 이 클라이언트는 어떤 경우에도 예외를 올려보내지 않는다.
    """

    SEARCH_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str, max_results: int = 5, timeout: int = 20):
        self.api_key = api_key
        self.max_results = max_results
        self.timeout = timeout

    def search(self, query: str) -> List[WebSearchResult]:
        query = (query or "").strip()
        if not query:
            return []

        payload = {
            "query": query,
            "max_results": self.max_results,
            "search_depth": "basic",
            "include_answer": False,
            "include_raw_content": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        try:
            response = requests.post(
                self.SEARCH_URL, json=payload, headers=headers, timeout=self.timeout
            )
            response.raise_for_status()
            return self._parse_results(response.json())
        except requests.exceptions.RequestException as e:
            logger.error(f"Web search request failed: {e}")
            return []
        except (TypeError, ValueError) as e:
            logger.error(f"Web search response parsing failed: {e}")
            return []

    @staticmethod
    def _parse_results(data: Any) -> List[WebSearchResult]:
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ValueError("web search response must contain a results list")

        results: List[WebSearchResult] = []
        seen_urls = set()
        for raw in data["results"]:
            if not isinstance(raw, dict):
                continue
            url = raw.get("url")
            if not _is_web_url(url) or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(
                WebSearchResult(
                    title=_as_string(raw.get("title"))[:MAX_RESULT_TITLE_CHARS],
                    url=url,
                    content=_as_string(raw.get("content"))[:MAX_RESULT_CONTENT_CHARS],
                    published_date=_as_string(raw.get("published_date")),
                )
            )
        return results


def _as_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_web_url(url: Any) -> bool:
    """답변과 출처 링크에 그대로 들어가므로, 평범한 http(s) URL 만 받는다."""
    if (
        not isinstance(url, str)
        or any(char in url for char in "<>|`")
        or any(char.isspace() for char in url)
    ):
        return False
    parsed = urlsplit(url)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
