import unittest

from shared.slack_events import (
    ChannelCreatedEvent,
    MentionEvent,
    MessageEvent,
    ReactionEvent,
    ShortcutPayload,
    SlackFile,
    ViewSubmission,
    is_edited_message,
    reply_target,
)
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_channel_created_event,
    create_sample_message_shortcut_body,
    create_sample_reaction_added_event,
    create_sample_reaction_removed_event,
    create_sample_view_submission_body,
)

# 새로 올라온 멘션 (실제 payload 형태)
NEW_APP_MENTION = {
    "type": "app_mention",
    "text": "<@UANNA> 빅챗 리마인더 테스트 <@U0001>",
    "user": "UQJ8HQJG5",
    "ts": "1689403771.805849",
    "channel": "C03SZTDEDK3",
    "event_ts": "1689403771.805849",
}

# 그 멘션을 고쳤을 때 다시 오는 이벤트 — 최상위에 edited 가 붙는다
EDITED_APP_MENTION = {
    **NEW_APP_MENTION,
    "edited": {"user": "UQJ8HQJG5", "ts": "1689403800.000000"},
}

# 메시지 수정 — 본문이 message 아래로 내려가고 subtype 이 붙는다
MESSAGE_CHANGED = {
    "type": "message",
    "subtype": "message_changed",
    "channel": "C03SZTDEDK3",
    "ts": "1689403800.000200",
    "message": {
        "type": "message",
        "text": "고친 글",
        "user": "UQJ8HQJG5",
        "ts": "1689403771.805849",
        "edited": {"user": "UQJ8HQJG5", "ts": "1689403800.000000"},
    },
    "previous_message": {"text": "원래 글", "ts": "1689403771.805849"},
}

NEW_MESSAGE = {
    "type": "message",
    "channel": "C03SZTDEDK3",
    "text": "새로 쓴 글",
    "user": "UQJ8HQJG5",
    "ts": "1689403771.805849",
}

# 이미지 첨부 글은 subtype 이 있어도 수정이 아니다 (자동 답글 대상)
FILE_SHARE_MESSAGE = {
    **NEW_MESSAGE,
    "subtype": "file_share",
    "files": [{"mimetype": "image/png", "url_private": "https://..."}],
}


class TestIsEditedMessage(unittest.TestCase):
    def test_edited_events(self):
        assert is_edited_message(EDITED_APP_MENTION)
        assert is_edited_message(MESSAGE_CHANGED)

    def test_new_events(self):
        assert not is_edited_message(NEW_APP_MENTION)
        assert not is_edited_message(NEW_MESSAGE)
        assert not is_edited_message(FILE_SHARE_MESSAGE)

    def test_ignores_falsy_and_malformed_payloads(self):
        assert not is_edited_message({})
        assert not is_edited_message(None)
        assert not is_edited_message({"edited": None})
        assert not is_edited_message({"message": None})


class TestMentionEvent(unittest.TestCase):
    def test_from_payload_inside_thread(self):
        event = MentionEvent.from_payload(
            create_sample_app_mention_event("<@UANNA> 안녕")
        )

        assert event == MentionEvent(
            text="<@UANNA> 안녕",
            user="UQJ8HQJG5",
            channel="C03SZTDEDK3",
            ts="1689403771.805849",
            thread_ts="1689403100.222939",
        )
        assert event.root_ts == "1689403100.222939"

    def test_root_ts_is_own_ts_outside_thread(self):
        event = MentionEvent.from_payload(NEW_APP_MENTION)

        assert event.thread_ts is None
        assert event.root_ts == event.ts == "1689403771.805849"


class TestReactionEvent(unittest.TestCase):
    def test_from_added_payload(self):
        event = ReactionEvent.from_payload(create_sample_reaction_added_event("gogo"))

        assert event == ReactionEvent(
            kind="reaction_added",
            user="UQJ8HQJG5",
            reaction="gogo",
            channel="C03SZTDEDK3",
            ts="1688801145.307229",
        )

    def test_from_removed_payload(self):
        event = ReactionEvent.from_payload(create_sample_reaction_removed_event("gogo"))

        assert event.kind == "reaction_removed"
        assert event.reaction == "gogo"


class TestMessageEvent(unittest.TestCase):
    def test_from_plain_message(self):
        event = MessageEvent.from_payload(NEW_MESSAGE)

        assert event == MessageEvent(
            channel="C03SZTDEDK3",
            ts="1689403771.805849",
            text="새로 쓴 글",
            user="UQJ8HQJG5",
        )
        assert event.files == []

    def test_from_file_share_prefers_download_url(self):
        payload = {
            **FILE_SHARE_MESSAGE,
            "files": [
                {
                    "mimetype": "image/png",
                    "url_private": "https://files.slack.com/a.png",
                    "url_private_download": "https://files.slack.com/download/a.png",
                },
                {
                    "mimetype": "image/jpeg",
                    "url_private": "https://files.slack.com/b.jpg",
                },
                {},
            ],
        }

        event = MessageEvent.from_payload(payload)

        assert event.subtype == "file_share"
        assert event.files == [
            SlackFile("image/png", "https://files.slack.com/download/a.png"),
            SlackFile("image/jpeg", "https://files.slack.com/b.jpg"),
            SlackFile("", ""),
        ]

    def test_bot_message_and_missing_fields(self):
        event = MessageEvent.from_payload(
            {
                "channel": "C1",
                "ts": "1.0",
                "bot_id": "B1",
                "subtype": "bot_message",
                "thread_ts": "0.9",
            }
        )

        assert event.user is None
        assert event.bot_id == "B1"
        assert event.thread_ts == "0.9"
        assert event.text == ""


class TestChannelCreatedEvent(unittest.TestCase):
    def test_from_payload(self):
        event = ChannelCreatedEvent.from_payload(
            create_sample_channel_created_event("C_NEW")
        )

        assert event == ChannelCreatedEvent(channel_id="C_NEW")


class TestShortcutPayload(unittest.TestCase):
    def test_message_outside_thread_uses_its_own_ts(self):
        payload = ShortcutPayload.from_payload(create_sample_message_shortcut_body())

        assert payload == ShortcutPayload(
            trigger_id="13345224609.738474920.8088930838d88f008e0",
            channel="C03SZTDEDK3",
            thread_ts="1688801145.307229",
            user="UQJ8HQJG5",
            response_url="https://hooks.slack.com/app/TQLEG4B38/1234567890/abcdefg",
        )

    def test_reply_inside_thread_uses_root_ts(self):
        payload = ShortcutPayload.from_payload(
            create_sample_message_shortcut_body(thread_ts="1688800000.000001")
        )

        assert payload.thread_ts == "1688800000.000001"


class TestViewSubmission(unittest.TestCase):
    def test_restores_context_from_private_metadata(self):
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )

        submission = ViewSubmission.from_payload(body)

        assert submission.channel == "C03SZTDEDK3"
        assert submission.thread_ts == "1688801145.307229"
        assert submission.user == "UQJ8HQJG5"
        assert (
            submission.response_url
            == "https://hooks.slack.com/app/TQLEG4B38/1234567890/abcdefg"
        )
        assert submission.values["bigchat_name"]["value"]["value"] == "AI 밋업"
        assert (
            submission.values["bigchat_date"]["value"]["selected_date"] == "2026-08-20"
        )
        assert submission.values["bigchat_start"]["value"]["selected_time"] == "19:00"
        assert submission.values["bigchat_end"]["value"]["selected_time"] == "21:00"


class TestReplyTarget(unittest.TestCase):
    def test_mention_replies_to_the_mentioning_message(self):
        event = create_sample_app_mention_event("<@UANNA> 안녕")

        assert reply_target(event) == ("C03SZTDEDK3", "1689403771.805849")

    def test_message_event(self):
        assert reply_target(NEW_MESSAGE) == ("C03SZTDEDK3", "1689403771.805849")

    def test_reaction_event_targets_the_reacted_item(self):
        event = create_sample_reaction_added_event("gogo")

        assert reply_target(event) == ("C03SZTDEDK3", "1688801145.307229")

    def test_channel_created_has_channel_but_no_ts(self):
        event = create_sample_channel_created_event("C_NEW")

        assert reply_target(event) == ("C_NEW", None)

    def test_interaction_payload_with_channel_id_and_thread_ts(self):
        assert reply_target({"channel_id": "C1", "thread_ts": "1.0"}) == ("C1", "1.0")

    def test_empty_event(self):
        assert reply_target({}) == (None, None)
