import json


def create_sample_message_shortcut_body(thread_ts=None):
    message = {
        "type": "message",
        "user": "U01BN035Y6L",
        "ts": "1688801145.307229",
        "text": "8월 빅챗을 소개합니다 ...",
    }
    if thread_ts:
        message["thread_ts"] = thread_ts
    return {
        "type": "message_action",
        "callback_id": "create_bigchat",
        "trigger_id": "13345224609.738474920.8088930838d88f008e0",
        "response_url": "https://hooks.slack.com/app/TQLEG4B38/1234567890/abcdefg",
        "user": {"id": "UQJ8HQJG5", "name": "roeniss"},
        "channel": {"id": "C03SZTDEDK3", "name": "bigchat"},
        "team": {"id": "TQLEG4B38", "domain": "ausg"},
        "message": message,
    }


def create_sample_view_submission_body(name, date, start, end):
    return {
        "type": "view_submission",
        "user": {"id": "UQJ8HQJG5", "name": "roeniss"},
        "team": {"id": "TQLEG4B38", "domain": "ausg"},
        "view": {
            "id": "V05JX2B8GPY",
            "type": "modal",
            "callback_id": "create_bigchat_modal",
            "private_metadata": json.dumps(
                {
                    "channel": "C03SZTDEDK3",
                    "thread_ts": "1688801145.307229",
                    "response_url": "https://hooks.slack.com/app/TQLEG4B38/1234567890/abcdefg",
                }
            ),
            "state": {
                "values": {
                    "bigchat_name": {
                        "value": {"type": "plain_text_input", "value": name}
                    },
                    "bigchat_date": {
                        "value": {"type": "datepicker", "selected_date": date}
                    },
                    "bigchat_start": {
                        "value": {"type": "timepicker", "selected_time": start}
                    },
                    "bigchat_end": {
                        "value": {"type": "timepicker", "selected_time": end}
                    },
                }
            },
        },
    }


def create_sample_app_mention_event(msg):
    return {
        "client_msg_id": "8fb50d48-f93d-4cca-b9ca-6965479e9a93",
        "type": "app_mention",
        "text": msg,
        "user": "UQJ8HQJG5",
        "ts": "1689403771.805849",
        "blocks": [],  # not used and too long, so skipped
        "team": "TQLEG4B38",
        "thread_ts": "1689403100.222939",
        "parent_user_id": "UQJ8HQJG5",
        "channel": "C03SZTDEDK3",
        "event_ts": "1689403771.805849",
    }


def create_sample_reaction_added_event(emoji_name):
    return {
        "type": "reaction_added",
        "user": "UQJ8HQJG5",
        "reaction": emoji_name,
        "item": {
            "type": "message",
            "channel": "C03SZTDEDK3",
            "ts": "1688801145.307229",
        },
        "item_user": "U01BN035Y6L",
        "event_ts": "1688833113.003600",
    }


def create_sample_reaction_removed_event(emoji_name):
    return {
        "type": "reaction_removed",
        "user": "UQJ8HQJG5",
        "reaction": emoji_name,
        "item": {
            "type": "message",
            "channel": "C03SZTDEDK3",
            "ts": "1688801145.307229",
        },
        "item_user": "U01BN035Y6L",
        "event_ts": "1688833113.003600",
    }


def create_sample_channel_created_event(channel_id):
    return {
        "type": "channel_created",
        "channel": {
            "id": channel_id,
            "name": "test-create-channel-2",
            "is_channel": True,
            "is_group": False,
            "is_im": False,
            "is_mpim": False,
            "is_private": False,
            "created": 1721484974,
            "is_archived": False,
            "is_general": False,
            "unlinked": 0,
            "name_normalized": "test-create-channel-2",
            "is_shared": False,
            "is_frozen": False,
            "is_org_shared": False,
            "is_pending_ext_shared": False,
            "pending_shared": [],
            "context_team_id": "TQLEG4B38",
            "updated": 1721484974161,
            "parent_conversation": None,
            "creator": "UQJ8HQJG5",
            "is_ext_shared": False,
            "shared_team_ids": ["TQLEG4B38"],
            "pending_connected_team_ids": [],
            "topic": {"value": "", "creator": "", "last_set": 0},
            "purpose": {"value": "", "creator": "", "last_set": 0},
            "previous_names": [],
        },
        "event_ts": "1721484974.006000",
    }
