"""Regressions across the real handlers, persistent state and reminders."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from features.bigchat.calendar import KST
from features.bigchat.errors import BigchatIntegrityError
from features.bigchat.handlers.abandon_bigchat import AbandonBigchat
from features.bigchat.handlers.join_bigchat import JoinBigchat
from features.bigchat.services.creation import register_early_reacted_users
from features.bigchat.services.reminders import RemindBigchat
from integrations.bigchat_store import BigchatStore
from integrations.slack import Message, Reaction
from test.fixtures.sheets import SheetsAPI
from test.fixtures.slack_events import create_sample_member

CHANNEL, THREAD, USER = "C_ORDER", "123.456", "U_ORDER"
CONTEXT = {"channel": CHANNEL, "thread_ts": THREAD}
TITLE = "Review 26-11-05 19:00~21:00"
SETTINGS = SimpleNamespace(ICS_TOKEN_SECRET="", PUBLIC_BASE_URL="")


def event(kind, timestamp):
    return {
        "type": kind,
        "reaction": "gogo",
        "item": {"channel": CHANNEL, "ts": THREAD},
        "user": USER,
        "event_ts": timestamp,
    }


def runtime():
    api = SheetsAPI()
    sid = BigchatStore(api).create(TITLE, **CONTEXT).worksheet_id
    slack, members = MagicMock(), MagicMock()
    slack.get_replies.return_value = [
        Message(ts=THREAD, thread_ts=THREAD, channel=CHANNEL, user="U_HOST", text=TITLE)
    ]
    members.find.return_value = create_sample_member()
    return api, sid, slack, members


def join(api, slack, members, timestamp):
    return JoinBigchat(
        event("reaction_added", timestamp),
        "gogo",
        slack,
        BigchatStore(api),
        members,
        settings=SETTINGS,
    ).run()


def cancel(api, slack, timestamp):
    return AbandonBigchat(
        event("reaction_removed", timestamp), "gogo", slack, BigchatStore(api)
    ).run()


def active_rows(api, sid):
    return [row[:4] for row in api.get_values(sid) if any(row[:4])]


def test_later_cancel_wins_when_join_is_still_loading_the_member():
    api, sid, slack, members = runtime()
    cancellation = MagicMock()

    def while_loading(_):
        cancel(api, cancellation, "200.000002")
        return create_sample_member()

    members.find.side_effect = while_loading
    assert join(api, slack, members, "200.000001") is False
    assert active_rows(api, sid) == []
    slack.send_message.assert_not_called()
    slack.send_message_only_visible_to_user.assert_not_called()


def test_old_delivery_cannot_override_a_newer_event_in_a_fresh_store():
    api, sid, slack, members = runtime()
    cancel(api, slack, "200.000002")
    assert join(api, slack, members, "200.000001") is False
    assert active_rows(api, sid) == []
    assert join(api, slack, members, "200.000003")
    assert cancel(api, slack, "200.000002") is False
    assert len(active_rows(api, sid)) == 1


def test_backfill_snapshot_cannot_undo_a_live_cancellation():
    api, sid, slack, members = runtime()
    slack.get_emoji.return_value = Reaction(name="gogo", users=[USER], count=1)

    def while_loading(_):
        cancel(api, MagicMock(), "200.000002")
        return create_sample_member()

    members.find.side_effect = while_loading
    register_early_reacted_users(
        slack, BigchatStore(api), members, "gogo", sid, CHANNEL, THREAD
    )
    assert active_rows(api, sid) == []
    slack.send_thread_message.assert_not_called()


def test_cancelled_email_note_is_not_a_reminder_recipient():
    api, sid, slack, members = runtime()
    member = create_sample_member().model_copy(update={"email": "user@example.test"})
    members.find.return_value = member
    join(api, slack, members, "200.000001")
    api.sheets[sid]["gridProperties"]["columnCount"] = 5
    api.sheets[sid]["rows"][0].append(member.email)
    cancel(api, slack, "200.000002")
    reader = SimpleNamespace(
        get_values=api.get_values,
        list_worksheets=lambda: [(sid, TITLE)],
        sheets_request=api.sheets_request,
        members_worksheet_id=api.members_worksheet_id,
    )
    members.email_to_slack_ids.return_value = {member.email: USER}
    result = RemindBigchat(slack, reader, members).run(
        now=datetime(2026, 11, 4, 18, tzinfo=KST)
    )
    assert result.sent_cnt == 0
    slack.send_direct_message.assert_not_called()


@pytest.mark.parametrize("operation", ["first_cancel", "join", "cancel", "rejoin"])
def test_lost_revision_response_and_duplicate_delivery_keep_one_latest_state(operation):
    api, sid, slack, members = runtime()
    if operation in {"cancel", "rejoin"}:
        join(api, slack, members, "200.000001")
    if operation == "rejoin":
        cancel(api, slack, "200.000002")
    api.fail_after = ":batchUpdate"
    action = lambda: (
        cancel(api, slack, "200.000003")
        if operation in {"first_cancel", "cancel"}
        else join(api, slack, members, "200.000003")
    )
    action()
    action()
    expected = [] if operation in {"first_cancel", "cancel"} else [USER]
    assert BigchatStore(api).active_user_ids(sid) == expected
    assert len(active_rows(api, sid)) == len(expected)


def test_newer_cancel_fences_an_in_flight_revision_update():
    api, sid, slack, members = runtime()
    join(api, slack, members, "200.000001")
    api.before_write = lambda: cancel(api, MagicMock(), "200.000003")
    assert join(api, slack, members, "200.000002") is False
    assert active_rows(api, sid) == []
    assert BigchatStore(api).active_user_ids(sid) == []


def test_newer_cancel_fences_an_in_flight_values_update(monkeypatch):
    api, sid, slack, members = runtime()
    join(api, slack, members, "200.000001")
    original = api.sheets_request
    intercepted = False

    def delayed_write(method, suffix, body=None):
        nonlocal intercepted
        if suffix == "/values:batchUpdateByDataFilter" and not intercepted:
            intercepted = True
            cancel(api, MagicMock(), "200.000003")
        return original(method, suffix, body)

    monkeypatch.setattr(api, "sheets_request", delayed_write)
    with pytest.raises(BigchatIntegrityError):
        BigchatStore(api).register(
            sid,
            USER,
            ["new", "company", "new@example.test", "phone"],
            **CONTEXT,
            event_ts="200.000002",
        )
    assert intercepted
    assert active_rows(api, sid) == []
    assert BigchatStore(api).active_user_ids(sid) == []


def test_reminders_use_active_slack_id_after_email_changes_and_sorting():
    api, sid, slack, members = runtime()
    join(api, slack, members, "200.000001")
    api.sheets[sid]["rows"][0][2] = "changed@example.test"
    api.sort_rows(sid)
    api.list_worksheets = lambda: [(sid, TITLE)]
    result = RemindBigchat(slack, api, members).run(
        now=datetime(2026, 11, 4, 18, tzinfo=KST)
    )
    assert result.sent_cnt == 1
    assert slack.send_direct_message.call_args.kwargs["user_id"] == USER
    members.email_to_slack_ids.assert_not_called()


def echo_participant_filters(api, monkeypatch, change):
    original = api.sheets_request

    def answer(method, suffix, body=None):
        response = original(method, suffix, body)
        if suffix == "/values:batchGetByDataFilter":
            for matched in response.get("valueRanges", []):
                for data_filter in matched.get("dataFilters", []):
                    change(data_filter)
        return response

    monkeypatch.setattr(api, "sheets_request", answer)


def add_output_only_fields(data_filter):
    lookup = data_filter["developerMetadataLookup"]
    lookup["metadataLocation"]["locationType"] = "SHEET"


def keep_only_metadata_id(data_filter):
    lookup = data_filter["developerMetadataLookup"]
    data_filter["developerMetadataLookup"] = {"metadataId": lookup["metadataId"]}


@pytest.mark.parametrize("change", [add_output_only_fields, keep_only_metadata_id])
def test_reminder_recipients_do_not_depend_on_the_echoed_filter_format(
    change, monkeypatch
):
    api, sid, slack, members = runtime()
    join(api, slack, members, "200.000001")
    echo_participant_filters(api, monkeypatch, change)
    assert BigchatStore(api).active_user_ids(sid) == [USER]


def test_reminder_recipients_reject_a_range_for_an_unknown_participant(monkeypatch):
    api, sid, slack, members = runtime()
    join(api, slack, members, "200.000001")

    def foreign(data_filter):
        data_filter["developerMetadataLookup"]["metadataId"] = 1

    echo_participant_filters(api, monkeypatch, foreign)
    with pytest.raises(BigchatIntegrityError, match="Ambiguous participant read"):
        BigchatStore(api).active_user_ids(sid)
