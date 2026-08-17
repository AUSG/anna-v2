import unittest

from util.slack_event import is_edited_message

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
