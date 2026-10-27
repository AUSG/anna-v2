import unittest
from unittest.mock import MagicMock, patch

import requests

from features.issues.models import Issue, IssueCreationFailed
from integrations.github import GithubClient


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

    def test_repo_is_normalised(self):
        assert GithubClient("gh_token", " /AUSG/anna-v2/ ").repo == "AUSG/anna-v2"


class TestCreateIssue(unittest.TestCase):
    @patch("integrations.github.requests.post")
    def test_create_issue(self, mock_post):
        mock_post.return_value = _response(201, CREATED)
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        issue = sut.create_issue(title="빅챗 리마인더가 두 번 와요", body="본문")

        assert issue == Issue(
            number=42,
            title="빅챗 리마인더가 두 번 와요",
            url="https://github.com/AUSG/anna-v2/issues/42",
        )
        assert (
            mock_post.call_args.args[0]
            == "https://api.github.com/repos/AUSG/anna-v2/issues"
        )
        assert mock_post.call_args.kwargs["json"] == {
            "title": "빅챗 리마인더가 두 번 와요",
            "body": "본문",
        }
        headers = mock_post.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer gh_token"
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    @patch("integrations.github.requests.post")
    def test_create_issue_with_labels(self, mock_post):
        mock_post.return_value = _response(201, CREATED)
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        sut.create_issue(title="제목", body="", labels=["bug"])

        assert mock_post.call_args.kwargs["json"]["labels"] == ["bug"]

    @patch("integrations.github.requests.post")
    def test_refuses_without_token(self, mock_post):
        sut = GithubClient("", "AUSG/anna-v2")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "토큰" in result.reason
        mock_post.assert_not_called()

    @patch("integrations.github.requests.post")
    def test_wraps_network_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectTimeout()
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "연결하지 못했어" in result.reason

    @patch("integrations.github.requests.post")
    def test_explains_bad_credentials(self, mock_post):
        mock_post.return_value = _response(401, {"message": "Bad credentials"})
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "토큰" in result.reason
        assert "401" in result.reason

    @patch("integrations.github.requests.post")
    def test_explains_missing_repo(self, mock_post):
        mock_post.return_value = _response(404, {"message": "Not Found"})
        sut = GithubClient("gh_token", "AUSG/anna-v3")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "AUSG/anna-v3" in result.reason

    @patch("integrations.github.requests.post")
    def test_explains_disabled_issues(self, mock_post):
        mock_post.return_value = _response(410, {"message": "Issues are disabled"})
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "이슈 기능이 꺼져" in result.reason

    @patch("integrations.github.requests.post")
    def test_explains_rejected_content(self, mock_post):
        mock_post.return_value = _response(422, {"message": "Validation Failed"})
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "거절했어" in result.reason

    @patch("integrations.github.requests.post")
    def test_explains_unknown_error(self, mock_post):
        mock_post.return_value = _response(500, {"message": "oops"})
        sut = GithubClient("gh_token", "AUSG/anna-v2")

        result = sut.create_issue(title="제목")

        assert isinstance(result, IssueCreationFailed)
        assert "500" in result.reason
