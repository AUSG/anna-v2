import unittest
from unittest.mock import MagicMock, patch

import requests

from implementation.github_client import GithubApiError, GithubClient


def _response(status_code, json_body=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = str(json_body)
    resp.json.return_value = json_body
    return resp


CREATED = {
    "number": 42,
    "title": "빅챗 리마인더가 두 번 와요",
    "html_url": "https://github.com/AUSG/anna-v2/issues/42",
}


class TestIsEnabled(unittest.TestCase):
    def test_needs_both_token_and_repo(self):
        assert GithubClient("gh_token", "AUSG/anna-v2").is_enabled()
        assert not GithubClient("", "AUSG/anna-v2").is_enabled()
        assert not GithubClient("gh_token", "").is_enabled()


class TestCreateIssue(unittest.TestCase):
    @patch("implementation.github_client.requests.post")
    def test_create_issue(self, mock_post):
        mock_post.return_value = _response(201, CREATED)
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        issue = sut.create_issue(title="빅챗 리마인더가 두 번 와요", body="본문")

        assert issue.number == 42
        assert issue.url == "https://github.com/AUSG/anna-v2/issues/42"
        assert (
            mock_post.call_args.args[0]
            == "https://api.github.com/repos/AUSG/anna-v2/issues"
        )
        assert mock_post.call_args.kwargs["json"] == {
            "title": "빅챗 리마인더가 두 번 와요",
            "body": "본문",
        }
        assert (
            mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer gh_token"
        )

    @patch("implementation.github_client.requests.post")
    def test_create_issue_with_labels(self, mock_post):
        mock_post.return_value = _response(201, CREATED)
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        sut.create_issue(title="제목", body="", labels=["bug"])

        assert mock_post.call_args.kwargs["json"]["labels"] == ["bug"]

    def test_refuses_without_token(self):
        sut = GithubClient("", "AUSG/anna-v2")

        with self.assertRaises(GithubApiError):
            sut.create_issue(title="제목")

    @patch("implementation.github_client.requests.post")
    def test_wraps_network_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectTimeout()
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        with self.assertRaises(GithubApiError) as ctx:
            sut.create_issue(title="제목")

        assert "연결하지 못했어" in ctx.exception.reason

    @patch("implementation.github_client.requests.post")
    def test_explains_bad_credentials(self, mock_post):
        mock_post.return_value = _response(401, {"message": "Bad credentials"})
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        with self.assertRaises(GithubApiError) as ctx:
            sut.create_issue(title="제목")

        assert "토큰" in ctx.exception.reason

    @patch("implementation.github_client.requests.post")
    def test_explains_missing_repo(self, mock_post):
        mock_post.return_value = _response(404, {"message": "Not Found"})
        sut = GithubClient("gh_token", "AUSG/anna-v3")

        with self.assertRaises(GithubApiError) as ctx:
            sut.create_issue(title="제목")

        assert "AUSG/anna-v3" in ctx.exception.reason

    @patch("implementation.github_client.requests.post")
    def test_explains_unknown_error(self, mock_post):
        mock_post.return_value = _response(500, {"message": "oops"})
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        with self.assertRaises(GithubApiError) as ctx:
            sut.create_issue(title="제목")

        assert "500" in ctx.exception.reason
