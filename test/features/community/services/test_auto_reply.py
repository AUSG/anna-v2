import pytest

from features.community.services.auto_reply import (
    KIMSUBIN_PERSONA_PROMPT,
    MAX_IMAGES,
    OPT_OUT_MARKER,
    REPLY_MAX_TOKENS,
    image_files,
    reply_content,
    should_auto_reply,
)
from shared.slack_events import MessageEvent, SlackFile

ANNA_ID = "UANNA"
CHANNEL_ID = "C03SZTDEDK3"
IMAGE = SlackFile(mimetype="image/png", url="https://files.slack.test/a.png")


def _event(**overrides):
    values = dict(channel=CHANNEL_ID, ts="1700000000.000100", text="새 글", user="U1")
    values.update(overrides)
    return MessageEvent(**values)


def _should(event):
    return should_auto_reply(event, anna_id=ANNA_ID, channel_id=CHANNEL_ID)


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        pytest.param(_event(), True, id="root-post"),
        pytest.param(
            _event(thread_ts="1700000000.000100"), True, id="root-with-own-ts"
        ),
        pytest.param(
            _event(subtype="file_share", files=[IMAGE]), True, id="file-share"
        ),
        pytest.param(_event(text="", files=[IMAGE]), True, id="image-only"),
        pytest.param(_event(channel="C_OTHER"), False, id="other-channel"),
        pytest.param(_event(text="오늘은 안나x"), False, id="opt-out-lower"),
        pytest.param(_event(text="안나X 오늘은 쉬어"), False, id="opt-out-upper"),
        pytest.param(_event(bot_id="B1"), False, id="bot-message"),
        pytest.param(_event(bot_id="B1", user=None), False, id="bot-without-user"),
        pytest.param(_event(subtype="message_changed"), False, id="edited-subtype"),
        pytest.param(_event(subtype="channel_join"), False, id="join-subtype"),
        pytest.param(_event(user=ANNA_ID), False, id="anna-own-post"),
        pytest.param(_event(thread_ts="1699999999.000000"), False, id="thread-reply"),
        pytest.param(_event(text=f"<@{ANNA_ID}> 질문이야"), False, id="anna-mentioned"),
        pytest.param(_event(text=""), False, id="empty-text"),
        pytest.param(_event(text=" \t\n"), False, id="whitespace-text"),
        pytest.param(
            _event(text="", files=[SlackFile(mimetype="application/pdf", url="u")]),
            False,
            id="empty-text-non-image-file",
        ),
    ],
)
def test_should_auto_reply(event, expected):
    assert _should(event) is expected


def test_constants_keep_their_contract():
    assert OPT_OUT_MARKER == "안나x"
    assert REPLY_MAX_TOKENS == 220
    assert MAX_IMAGES == 4
    assert "김수빈" in KIMSUBIN_PERSONA_PROMPT


def test_anna_mention_check_is_skipped_without_anna_id():
    event = _event(text="<@UANNA> 안녕")
    assert should_auto_reply(event, anna_id="", channel_id=CHANNEL_ID) is True


def test_image_files_keeps_only_images_up_to_the_limit():
    files = [
        SlackFile(mimetype="application/pdf", url="https://files.slack.test/doc.pdf"),
        *[
            SlackFile(mimetype="image/jpeg", url=f"https://files.slack.test/{i}.jpg")
            for i in range(6)
        ],
    ]
    kept = image_files(_event(files=files))
    assert kept == files[1 : 1 + MAX_IMAGES]


def test_reply_content_strips_mentions():
    assert reply_content(_event(text="<@U1> 이거 봐 <@U2> ")) == "이거 봐"
