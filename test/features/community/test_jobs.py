import pytest

from features.community import jobs
from test.fixtures.runtime import fake_dependencies


def test_daily_digest_posts_only_nonempty_content():
    dependencies = fake_dependencies()
    dependencies._get_qa_client.return_value.daily_digest.return_value = "오늘의 핫스레드"
    jobs.post_daily_digest(dependencies)
    dependencies.SlackClient.return_value.post_markdown.assert_called_once_with(
        "C_DIGEST", "오늘의 핫스레드"
    )
    dependencies.create_web_client.return_value.chat_postMessage.assert_not_called()


@pytest.mark.parametrize("text", ["", None])
def test_empty_digest_does_not_post(text):
    dependencies = fake_dependencies()
    dependencies._get_qa_client.return_value.daily_digest.return_value = text
    jobs.post_daily_digest(dependencies)
    dependencies.SlackClient.assert_not_called()
    dependencies.create_web_client.return_value.chat_postMessage.assert_not_called()


def test_digest_failure_notifies_admin():
    dependencies = fake_dependencies()
    dependencies._get_qa_client.return_value.daily_digest.side_effect = RuntimeError(
        "digest failed"
    )
    jobs.post_daily_digest(dependencies)
    kwargs = (
        dependencies.create_web_client.return_value.chat_postMessage.call_args.kwargs
    )
    assert kwargs["channel"] == "C_ADMIN"
    assert "digest failed" in kwargs["text"]
    assert kwargs["unfurl_links"] is False and kwargs["unfurl_media"] is False
