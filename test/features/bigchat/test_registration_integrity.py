from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from features.bigchat.handlers.abandon_bigchat import AbandonBigchat
from features.bigchat.handlers.join_bigchat import JoinBigchat
from features.bigchat.services.creation import register_early_reacted_users
from features.members.services.directory import Member
from integrations.google_sheets import GoogleSpreadsheetClient
from integrations.slack import Message, Reaction
from test.fixtures.sheets import SheetsAPI

CHANNEL, THREAD = "C_TEST", "123.456"
TITLE = "AI 밋업 26-08-20 19:00~21:00"
MEMBER = Member(
    kor_name="Alice",
    eng_name="Alice",
    email="a@example.test",
    phone="010-1111-1111",
    school_name_or_company_name="Company",
)


def setup(monkeypatch):
    api = SheetsAPI()
    client = GoogleSpreadsheetClient.__new__(GoogleSpreadsheetClient)
    client.spreadsheet_id = api.spreadsheet_id
    client.members_worksheet_id = api.members_worksheet_id
    monkeypatch.setattr(client, "sheets_request", api.sheets_request)
    monkeypatch.setattr(client, "get_worksheet_title", api.get_worksheet_title)
    slack, members = MagicMock(), MagicMock()
    members.find.return_value = MEMBER
    slack.get_permalink.return_value = None
    event = {
        "type": "reaction_added",
        "reaction": "gogo",
        "user": "U_A",
        "item": {"channel": CHANNEL, "ts": THREAD},
    }
    return api, client, slack, members, event


def messages(text):
    return [
        Message(ts=THREAD, thread_ts=THREAD, channel=CHANNEL, user="U_OTHER", text=text)
    ]


@pytest.mark.parametrize(
    "text",
    [
        "https://docs.google.com/spreadsheets/d/unrelated-document/edit#gid=42",
        "https://docs.google.com/spreadsheets/d/configured-document/edit#gid=42",
        "새로운 빅챗, 등록 완료! <https://docs.google.com/spreadsheets/d/configured-document/edit#gid=123|시트>",
        "https://docs.google.com/spreadsheets/d/configured-document/edit#gid=0",
    ],
)
@pytest.mark.parametrize("cancel", [False, True])
def test_message_links_never_establish_write_authority(text, cancel, monkeypatch):
    api, client, slack, members, event = setup(monkeypatch)
    api.add_legacy_sheet(42, [["protected member directory"]])
    api.add_legacy_sheet(123, [["unbound worksheet"]])
    slack.get_replies.return_value = messages(text)
    if cancel:
        event["type"] = "reaction_removed"
        handler = AbandonBigchat(event, "gogo", slack, client)
    else:
        handler = JoinBigchat(event, "gogo", slack, client, members)
    assert handler.run() is False
    assert all(method == "get" for method, _, _ in api.calls)
    assert members.mock_calls == []
    assert slack.mock_calls == []
    assert api.metadata == {}
    assert api.get_values(42) == [["protected member directory"]]
    assert api.get_values(123) == [["unbound worksheet"]]


def test_backfill_and_event_share_identity_and_cancellation_survives_profile_removal(
    monkeypatch,
):
    api, client, slack, members, event = setup(monkeypatch)
    sheet = client.create_bigchat_sheet(TITLE, channel=CHANNEL, thread_ts=THREAD)
    slack.get_emoji.return_value = Reaction(name="gogo", users=["U_A"], count=1)
    register_early_reacted_users(slack, client, members, "gogo", sheet, CHANNEL, THREAD)
    # Even a conflicting link cannot redirect a legitimately bound thread.
    slack.get_replies.return_value = messages(
        "https://docs.google.com/spreadsheets/d/foreign/edit#gid=42"
    )
    members.find.return_value = MEMBER.model_copy(
        update={"school_name_or_company_name": "New company"}
    )
    assert JoinBigchat(
        event,
        "gogo",
        slack,
        client,
        members,
        settings=SimpleNamespace(ICS_TOKEN_SECRET="", PUBLIC_BASE_URL=""),
    ).run()
    rows = [row for row in api.get_values(sheet) if any(row)]
    assert rows == [["Alice", "New company", "a@example.test", "010-1111-1111"]]
    assert "이미 등록되어 있어" in slack.send_message.call_args.kwargs["msg"]
    members.find.side_effect = AssertionError(
        "Cancellation must not read current member profile"
    )
    event["type"] = "reaction_removed"
    assert AbandonBigchat(event, "gogo", slack, client).run()
    assert api.get_values(sheet) == [["", "", "", ""]]
