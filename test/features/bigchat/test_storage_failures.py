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
from features.bigchat.presentation.messages import bigchat_created_message
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


CHANNEL, THREAD = "C_TEST", "123.456"


def reaction_handler(operation, slack, store, members):
    event = {
        "type": "reaction_added" if operation == "join" else "reaction_removed",
        "reaction": "gogo",
        "item": {"channel": CHANNEL, "ts": THREAD},
        "user": "U_A",
    }
    loading = LoadingEmoji(slack, CHANNEL, THREAD)
    if operation == "join":
        return JoinBigchat(event, "gogo", slack, store, members, loading)
    return AbandonBigchat(event, "gogo", slack, store, loading)


def thread_of(*texts):
    return [
        Message(
            ts=f"123.{456 + i}",
            thread_ts=THREAD,
            channel=CHANNEL,
            user="U_OTHER",
            text=text,
        )
        for i, text in enumerate(texts)
    ]


def sheets_unavailable(api, monkeypatch, status=503):
    def fail(*args, **kwargs):
        raise api_error(status)

    monkeypatch.setattr("integrations.sheets_retry.time.sleep", lambda _: None)
    monkeypatch.setattr(api, "sheets_request", fail)


@pytest.mark.parametrize("operation", ["join", "cancel"])
@pytest.mark.parametrize("status", [403, 429, 503])
@pytest.mark.parametrize("posted", ["casual", "other_post_link", "longer_gid"])
def test_casual_gogo_stays_silent_while_sheets_is_unavailable(
    operation, status, posted, monkeypatch
):
    """일반 대화에서도 :gogo:를 쓰므로, 모집글인지 확인하지 못해도 안내하지 않는다."""
    api = SheetsAPI()
    store = BigchatStore(api)
    slack, members = MagicMock(), MagicMock()
    text = {
        "casual": "오늘 점심 고고!",
        "other_post_link": store.sheet_url(CHANNEL, "999.999"),
        "longer_gid": store.sheet_url(CHANNEL, THREAD) + "7",
    }[posted]
    slack.get_replies.return_value = thread_of("점심 메뉴 정하자", text)
    sheets_unavailable(api, monkeypatch, status)
    assert reaction_handler(operation, slack, store, members).run() is False
    slack.get_replies.assert_called_once_with(channel=CHANNEL, thread_ts=THREAD)
    slack.send_message.assert_not_called()
    slack.send_message_only_visible_to_user.assert_not_called()
    slack.add_emoji.assert_not_called()
    members.find.assert_not_called()


@pytest.mark.parametrize("operation", ["join", "cancel"])
def test_bigchat_post_still_gets_the_notice_while_sheets_is_unavailable(
    operation, monkeypatch
):
    """봇이 이 모집글에 올린 시트 링크가 있으면 다른 저장소 오류처럼 스레드에 안내한다."""
    api = SheetsAPI()
    created = BigchatStore(api).create(TITLE, channel=CHANNEL, thread_ts=THREAD)
    slack, members = MagicMock(), MagicMock()
    slack.get_replies.return_value = thread_of(
        "빅챗 모집합니다!",
        bigchat_created_message(created.sheet_url, created.sheet_name),
    )
    sheets_unavailable(api, monkeypatch)
    store = BigchatStore(api)  # 이벤트마다 새로 만드는 저장소
    assert reaction_handler(operation, slack, store, members).run() is False
    slack.send_message.assert_called_once()
    msg = slack.send_message.call_args.kwargs["msg"]
    assert msg.startswith("<@U_A>")
    assert "접근하거나" in msg
    assert "삭제" not in msg
    slack.send_message_only_visible_to_user.assert_not_called()
    slack.add_emoji.assert_not_called()
    members.find.assert_not_called()


def test_unreadable_thread_while_sheets_is_unavailable_stays_silent(monkeypatch):
    api = SheetsAPI()
    store = BigchatStore(api)
    slack = MagicMock()
    slack.get_replies.side_effect = RuntimeError("Slack unavailable")
    sheets_unavailable(api, monkeypatch)
    assert reaction_handler("join", slack, store, MagicMock()).run() is False
    slack.send_message.assert_not_called()
    slack.send_message_only_visible_to_user.assert_not_called()
