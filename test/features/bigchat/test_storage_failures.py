"""Real store + API oracle through every user-facing creation/reaction path."""

import copy
import json
from unittest.mock import MagicMock

import pytest

from features.bigchat.handlers.abandon_bigchat import AbandonBigchat
from features.bigchat.handlers.create_bigchat_modal import (
    SubmitCreateBigchatModal,
    normalize_view_body,
)
from features.bigchat.handlers.create_bigchat_sheet import CreateBigchatSheet
from features.bigchat.handlers.join_bigchat import JoinBigchat
from integrations.bigchat_store import BigchatStore
from integrations.slack import Message
from shared.loading_emoji import LoadingEmoji
from test.fixtures.sheets import SheetsAPI, api_error
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_member,
    create_sample_view_submission_body,
)

TITLE = "AI 밋업 26-08-20 19:00~21:00"


@pytest.mark.parametrize("entry", ["mention", "modal_response", "modal_ephemeral"])
@pytest.mark.parametrize("failure", ["duplicate", "deleted", "permission"])
def test_creation_errors_are_announced_without_success_or_backfill(
    entry, failure, monkeypatch
):
    api = SheetsAPI()
    store = BigchatStore(api)
    slack, members, ack = MagicMock(), MagicMock(), MagicMock()
    if entry == "mention":
        event = create_sample_app_mention_event("<@ANNA> 새로운 빅챗 " + TITLE)
        channel, thread = event["channel"], event.get("thread_ts") or event["ts"]
        handler = CreateBigchatSheet(event, slack, store, members, "gogo")
        run = handler.handle_mention
    else:
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )
        if entry == "modal_ephemeral":
            metadata = json.loads(body["view"]["private_metadata"])
            metadata.pop("response_url")
            body["view"]["private_metadata"] = json.dumps(metadata)
        event = normalize_view_body(body)
        channel, thread = event["channel"], event["ts"]
        handler = SubmitCreateBigchatModal(event, ack, slack, store, members, "gogo")
        run = handler.run

    if failure == "duplicate":
        api.add_legacy_sheet(123, [["unrelated participant"]], title=TITLE)
    elif failure == "deleted":
        created = store.create(TITLE, channel=channel, thread_ts=thread)
        api.delete_sheet(created.worksheet_id)
    else:

        def denied(*args, **kwargs):
            raise api_error(403)

        monkeypatch.setattr(api, "sheets_request", denied)
    before = copy.deepcopy((api.sheets, api.metadata))
    assert run() is False
    assert (api.sheets, api.metadata) == before
    slack.send_message.assert_not_called()
    slack.send_thread_message.assert_not_called()
    slack.get_emoji.assert_not_called()
    members.find.assert_not_called()
    if entry == "modal_response":
        slack.send_response_url_message.assert_called_once()
        msg = slack.send_response_url_message.call_args.kwargs["msg"]
    else:
        slack.send_message_only_visible_to_user.assert_called_once()
        msg = slack.send_message_only_visible_to_user.call_args.kwargs["msg"]
    expected = {"duplicate": "같은 이름", "deleted": "삭제", "permission": "접근하거나"}
    assert expected[failure] in msg
    assert "simulated API error" not in msg
    if entry != "mention":
        ack.assert_called_once_with()


@pytest.mark.parametrize("operation", ["join", "cancel"])
@pytest.mark.parametrize("timing", ["before_lookup", "before_write"])
def test_deleted_tab_produces_notice_through_the_actual_store(operation, timing):
    api = SheetsAPI()
    store = BigchatStore(api)
    slack, members = MagicMock(), MagicMock()
    channel, thread = "C_TEST", "123.456"
    created = store.create(TITLE, channel=channel, thread_ts=thread)
    sid = created.worksheet_id
    user = "U_REGISTERED" if operation == "cancel" else "U_NEW"
    member = create_sample_member()
    members.find.return_value = member
    store.register(
        sid,
        "U_REGISTERED",
        member.transform_for_spreadsheet(),
        channel=channel,
        thread_ts=thread,
    )
    slack.get_replies.return_value = [
        Message(
            ts=thread,
            thread_ts=thread,
            channel=channel,
            user="U_HOST",
            text="Introduction",
        )
    ]
    event = {
        "type": "reaction_added" if operation == "join" else "reaction_removed",
        "reaction": "gogo",
        "item": {"channel": channel, "ts": thread},
        "user": user,
    }
    loading = LoadingEmoji(slack, channel, thread)
    handler = (
        JoinBigchat(event, "gogo", slack, store, members, loading)
        if operation == "join"
        else AbandonBigchat(event, "gogo", slack, store, loading)
    )
    if timing == "before_lookup":
        api.delete_sheet(sid)
    else:
        api.before_write = lambda: api.delete_sheet(sid)
    assert handler.run() is False
    assert api.sheets == {}
    slack.send_message.assert_called_once()
    assert "삭제" in slack.send_message.call_args.kwargs["msg"]
    slack.send_message_only_visible_to_user.assert_not_called()
    if timing == "before_write":
        slack.add_emoji.assert_called_once()
        slack.remove_emoji.assert_called_once()
    else:
        slack.add_emoji.assert_not_called()


@pytest.mark.parametrize("operation", ["join", "cancel"])
def test_api_permission_failure_is_not_reported_as_a_deleted_sheet(
    operation, monkeypatch
):
    api = SheetsAPI()
    store = BigchatStore(api)
    slack = MagicMock()
    event = {
        "type": "reaction_added" if operation == "join" else "reaction_removed",
        "reaction": "gogo",
        "item": {"channel": "C_TEST", "ts": "123.456"},
        "user": "U_A",
    }

    def denied(*args, **kwargs):
        raise api_error(403)

    monkeypatch.setattr(api, "sheets_request", denied)
    handler = (
        JoinBigchat(event, "gogo", slack, store, MagicMock())
        if operation == "join"
        else AbandonBigchat(event, "gogo", slack, store)
    )
    assert handler.run() is False
    msg = slack.send_message.call_args.kwargs["msg"]
    assert "접근하거나" in msg
    assert "삭제" not in msg
    slack.send_message_only_visible_to_user.assert_not_called()
