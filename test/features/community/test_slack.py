import base64
from unittest.mock import MagicMock, call

import pytest

from features.community.presentation.messages import new_channel_message
from features.community.services.auto_reply import (
    KIMSUBIN_PERSONA_PROMPT,
    REPLY_MAX_TOKENS,
)
from features.community.slack import announce_new_channel_created, subin_like_response
from features.questions.ports import QAGateway
from shared.slack_events import ChannelCreatedEvent, MessageEvent, SlackFile
from test.fixtures.runtime import fake_slack
from test.fixtures.slack_events import create_sample_channel_created_event

ANNA_ID = "UANNA"
CHANNEL_ID = "C03SZTDEDK3"
FREETALK = "C_FREETALK"
IMAGE = SlackFile(mimetype="image/png", url="https://files.slack.test/a.png")


def _event(**overrides):
    values = dict(channel=CHANNEL_ID, ts="1700000000.000100", text="새 글", user="U1")
    values.update(overrides)
    return MessageEvent(**values)


def _make(answer="수빈 답글"):
    slack = fake_slack()
    qa = MagicMock(spec=QAGateway)
    qa.generate.return_value = answer
    return slack, qa


def _respond(event, slack, qa):
    return subin_like_response(event, slack, qa, anna_id=ANNA_ID, channel_id=CHANNEL_ID)


def _data_url(data, mimetype="image/png"):
    return f"data:{mimetype};base64,{base64.b64encode(data).decode('ascii')}"


class TestAnnounceNewChannelCreated:
    def test_posts_announcement_to_freetalk_channel(self):
        event = ChannelCreatedEvent.from_payload(
            create_sample_channel_created_event("C1234567890")
        )
        slack = fake_slack()

        result = announce_new_channel_created(event, slack, freetalk_channel=FREETALK)

        assert result is True
        slack.send_channel_message.assert_called_once_with(
            FREETALK, new_channel_message("C1234567890")
        )
        assert (
            slack.send_channel_message.call_args.args[1]
            == "새로운 채널이 만들어졌어! <#C1234567890>"
        )


class TestSubinLikeResponse:
    @pytest.mark.parametrize(
        "event",
        [
            pytest.param(_event(channel="C_OTHER"), id="other-channel"),
            pytest.param(_event(text="오늘은 안나x"), id="opt-out-lower"),
            pytest.param(_event(text="안나X 오늘은 쉬어"), id="opt-out-upper"),
            pytest.param(_event(bot_id="B1"), id="bot-message"),
            pytest.param(
                _event(subtype="message_changed"), id="non-file-share-subtype"
            ),
            pytest.param(_event(user=ANNA_ID), id="anna-own-post"),
            pytest.param(_event(thread_ts="1699999999.000000"), id="thread-reply"),
            pytest.param(_event(text=f"<@{ANNA_ID}> 질문이야"), id="anna-mentioned"),
            pytest.param(_event(text=" "), id="empty-text-without-images"),
        ],
    )
    def test_excluded_posts_do_nothing(self, event):
        slack, qa = _make()

        assert _respond(event, slack, qa) is False

        qa.generate.assert_not_called()
        slack.download_file.assert_not_called()
        slack.send_thread_message.assert_not_called()

    def test_success_posts_generated_answer_as_thread_reply(self):
        slack, qa = _make("React가 표준인 것 같아요 :thinking_face:")
        event = _event(text="<@U2> 웹 프레임워크 뭐 쓰세요? <@U3>")

        assert _respond(event, slack, qa) is True

        qa.generate.assert_called_once_with(
            content="웹 프레임워크 뭐 쓰세요?",
            system_prompt=KIMSUBIN_PERSONA_PROMPT,
            max_tokens=REPLY_MAX_TOKENS,
            images=None,
        )
        slack.download_file.assert_not_called()
        slack.send_thread_message.assert_called_once_with(
            CHANNEL_ID, event.ts, "React가 표준인 것 같아요 :thinking_face:"
        )

    def test_file_share_post_passes_images_as_data_urls(self):
        slack, qa = _make()
        slack.download_file.return_value = b"\x89PNG"
        jpeg = SlackFile(mimetype="image/jpeg", url="https://files.slack.test/b.jpg")
        event = _event(subtype="file_share", text="이거 봐", files=[IMAGE, jpeg])

        assert _respond(event, slack, qa) is True

        assert slack.download_file.call_args_list == [call(IMAGE.url), call(jpeg.url)]
        assert qa.generate.call_args.kwargs["images"] == [
            _data_url(b"\x89PNG", "image/png"),
            _data_url(b"\x89PNG", "image/jpeg"),
        ]
        slack.send_thread_message.assert_called_once_with(CHANNEL_ID, event.ts, "수빈 답글")

    def test_at_most_four_images_and_non_image_files_are_ignored(self):
        slack, qa = _make()
        slack.download_file.side_effect = lambda url: url.encode()
        files = [
            SlackFile(mimetype="application/pdf", url="https://files.slack.test/d.pdf"),
            *[
                SlackFile(mimetype="image/png", url=f"https://files.slack.test/{i}.png")
                for i in range(6)
            ],
        ]
        event = _event(subtype="file_share", text="", files=files)

        assert _respond(event, slack, qa) is True

        assert slack.download_file.call_args_list == [call(f.url) for f in files[1:5]]
        assert qa.generate.call_args.kwargs["images"] == [
            _data_url(f.url.encode()) for f in files[1:5]
        ]

    def test_failed_or_empty_download_is_skipped(self):
        slack, qa = _make()
        ok = SlackFile(mimetype="image/png", url="https://files.slack.test/ok.png")
        failed = SlackFile(mimetype="image/png", url="https://files.slack.test/no.png")
        no_url = SlackFile(mimetype="image/png", url="")
        slack.download_file.side_effect = lambda url: b"ok" if url == ok.url else None
        event = _event(subtype="file_share", files=[failed, no_url, ok])

        assert _respond(event, slack, qa) is True

        assert slack.download_file.call_args_list == [call(failed.url), call(ok.url)]
        assert qa.generate.call_args.kwargs["images"] == [_data_url(b"ok")]

    def test_image_without_mimetype_defaults_to_png(self):
        slack, qa = _make()
        slack.download_file.return_value = b"x"
        event = _event(
            files=[SlackFile(mimetype="image/", url="https://files.slack.test/x")]
        )

        assert _respond(event, slack, qa) is True
        assert qa.generate.call_args.kwargs["images"] == [_data_url(b"x", "image/")]

    def test_all_downloads_failing_sends_no_images(self):
        slack, qa = _make()
        slack.download_file.return_value = None
        event = _event(subtype="file_share", files=[IMAGE])

        assert _respond(event, slack, qa) is True
        assert qa.generate.call_args.kwargs["images"] is None

    @pytest.mark.parametrize("answer", ["", None])
    def test_empty_answer_posts_nothing(self, answer):
        slack, qa = _make(answer)

        assert _respond(_event(), slack, qa) is False

        qa.generate.assert_called_once()
        slack.send_thread_message.assert_not_called()
