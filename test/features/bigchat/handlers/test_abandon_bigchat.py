from unittest.mock import MagicMock

import pytest
from gspread.exceptions import WorksheetNotFound

from features.bigchat.handlers.abandon_bigchat import AbandonBigchat
from shared.loading_emoji import LoadingEmoji
from test.fixtures.slack_events import create_sample_reaction_removed_event


def runtime():
    event = create_sample_reaction_removed_event("gogo")
    slack, members, sheets = MagicMock(), MagicMock(), MagicMock()
    sheets.find_bigchat.return_value = 161837744
    handler = AbandonBigchat(
        event,
        "gogo",
        slack,
        sheets,
        loading_emoji=LoadingEmoji(
            slack, event["item"]["channel"], event["item"]["ts"]
        ),
    )
    return event, handler, slack, members, sheets


def test_cancellation_uses_slack_identity_without_profile_or_message_lookup():
    event, handler, slack, members, sheets = runtime()
    assert handler.run()
    sheets.cancel_bigchat.assert_called_once_with(
        161837744,
        event["user"],
        channel=event["item"]["channel"],
        thread_ts=event["item"]["ts"],
    )
    members.find.assert_not_called()
    slack.get_replies.assert_not_called()
    slack.send_message_only_visible_to_user.assert_called_once()
    slack.add_emoji.assert_called_once()
    slack.remove_emoji.assert_called_once()
    calls = [call[0] for call in slack.mock_calls]
    assert (
        calls.index("add_emoji")
        < calls.index("send_message_only_visible_to_user")
        < calls.index("remove_emoji")
    )


def test_unbound_thread_does_not_load_messages_or_modify_storage():
    event, handler, slack, members, sheets = runtime()
    sheets.find_bigchat.return_value = None
    assert handler.run() is False
    sheets.find_bigchat.assert_called_once_with(
        channel=event["item"]["channel"], thread_ts=event["item"]["ts"]
    )
    sheets.cancel_bigchat.assert_not_called()
    assert slack.mock_calls == []
    assert members.mock_calls == []


def test_unrelated_reaction_does_not_access_binding_or_storage():
    _, handler, slack, members, sheets = runtime()
    handler.reaction = "other"
    assert handler.run() is False
    assert sheets.mock_calls == []
    assert slack.mock_calls == []
    assert members.mock_calls == []


def test_deleted_sheet_notice_and_loading_cleanup():
    _, handler, slack, _, sheets = runtime()
    sheets.cancel_bigchat.side_effect = WorksheetNotFound("gone")
    assert handler.run() is False
    assert "등록을 취소하지 못했어" in slack.send_message.call_args.kwargs["msg"]
    slack.send_message_only_visible_to_user.assert_not_called()
    slack.remove_emoji.assert_called_once()


def test_storage_failure_does_not_report_success_and_clears_loading():
    _, handler, slack, _, sheets = runtime()
    sheets.cancel_bigchat.side_effect = RuntimeError("unavailable")
    with pytest.raises(RuntimeError):
        handler.run()
    slack.send_message_only_visible_to_user.assert_not_called()
    slack.remove_emoji.assert_called_once()
