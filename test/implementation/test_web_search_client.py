from unittest.mock import MagicMock, patch

import requests

from implementation.web_search_client import (
    MAX_RESULT_CONTENT_CHARS,
    WebSearchClient,
    WebSearchResult,
)


def _response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_search_sends_query_with_bearer_key_and_parses_results():
    response = _response(
        {
            "results": [
                {
                    "title": "AWS re:Invent 2026",
                    "url": "https://reinvent.awsevents.com/",
                    "content": "x" * (MAX_RESULT_CONTENT_CHARS + 50),
                    "published_date": "2026-09-01",
                    "score": 0.9,
                },
                {"title": "중복", "url": "https://reinvent.awsevents.com/"},
                {"title": "스키마 없음", "url": "javascript:alert(1)"},
                {"title": "슬랙 문법 깨짐", "url": "https://a.test/<x>|y"},
                "garbage",
                {"title": "URL 없음"},
            ]
        }
    )
    with patch(
        "implementation.web_search_client.requests.post", return_value=response
    ) as post:
        results = WebSearchClient("key", max_results=3).search("  re:Invent 2026  ")

    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer key"}
    assert post.call_args.kwargs["json"]["query"] == "re:Invent 2026"
    assert post.call_args.kwargs["json"]["max_results"] == 3
    assert results == [
        WebSearchResult(
            title="AWS re:Invent 2026",
            url="https://reinvent.awsevents.com/",
            content="x" * MAX_RESULT_CONTENT_CHARS,
            published_date="2026-09-01",
        )
    ]


def test_search_skips_request_for_blank_query():
    with patch("implementation.web_search_client.requests.post") as post:
        assert WebSearchClient("key").search("   ") == []

    post.assert_not_called()


def test_search_returns_empty_on_request_failure():
    with patch(
        "implementation.web_search_client.requests.post",
        side_effect=requests.exceptions.ConnectionError("down"),
    ):
        assert WebSearchClient("key").search("질문") == []


def test_search_returns_empty_on_malformed_response():
    with patch(
        "implementation.web_search_client.requests.post",
        return_value=_response({"unexpected": True}),
    ):
        assert WebSearchClient("key").search("질문") == []
