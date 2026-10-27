import pytest

from features.community import jobs
from test.fixtures.runtime import fake_runtime


def test_daily_digest_posts_only_nonempty_content():
    runtime = fake_runtime()
    runtime.qa().daily_digest.return_value = "오늘의 핫스레드"

    jobs.post_daily_digest(runtime)

    runtime.slack.send_markdown.assert_called_once_with("C_DIGEST", "오늘의 핫스레드")
    runtime.slack.send_channel_message.assert_not_called()
    # 잡은 스스로 WebClient 를 만들어 슬랙 클라이언트를 얻는다
    assert len(runtime.web_clients) == 1


@pytest.mark.parametrize("text", ["", None])
def test_empty_digest_does_not_post(text):
    runtime = fake_runtime()
    runtime.qa().daily_digest.return_value = text

    jobs.post_daily_digest(runtime)

    runtime.slack.send_markdown.assert_not_called()
    runtime.slack.send_channel_message.assert_not_called()


def test_digest_failure_notifies_admin_with_traceback():
    runtime = fake_runtime()
    runtime.qa().daily_digest.side_effect = RuntimeError("digest failed")

    jobs.post_daily_digest(runtime)

    runtime.slack.send_markdown.assert_not_called()
    runtime.slack.send_channel_message.assert_called_once()
    channel, text = runtime.slack.send_channel_message.call_args.args
    assert channel == "C_ADMIN"
    assert "데일리 핫스레드 게시" in text
    assert "digest failed" in text
    assert "RuntimeError" in text
    assert "Traceback" in text


def test_post_failure_notifies_admin():
    runtime = fake_runtime()
    runtime.qa().daily_digest.return_value = "오늘의 핫스레드"
    runtime.slack.send_markdown.side_effect = RuntimeError("post failed")

    jobs.post_daily_digest(runtime)

    channel, text = runtime.slack.send_channel_message.call_args.args
    assert channel == "C_ADMIN"
    assert "post failed" in text
