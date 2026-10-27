"""빅챗 생성 응답 전문과 외부 호출 순서를 fixture와 비교한다."""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from features.bigchat.slack import (
    SubmitCreateBigchatModal,
    normalize_view_body,
    CreateBigchatSheet,
)
from integrations.slack import Reaction
from test.fixtures.slack_events import (
    create_sample_app_mention_event,
    create_sample_member,
    create_sample_view_submission_body,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "bigchat_creation_behavior.json"
CASES = [
    {"id": "mention-multiline", "kind": "mention", "multiline": True},
    {"id": "modal-success", "kind": "modal", "users": ["U01BN035Y6L"]},
    {
        "id": "mention-ephemeral-unexpected",
        "kind": "mention",
        "users": ["U_LEFT", "U_OK"],
        "failure": "ephemeral",
    },
    {
        "id": "mention-group-message-failure",
        "kind": "mention",
        "users": ["U01BN035Y6L"],
        "failure": "group",
    },
    {"id": "modal-response-url-failure", "kind": "modal", "failure": "response_url"},
    {"id": "mention-reaction-read-failure", "kind": "mention", "failure": "reaction"},
]


def capture_behavior(case):
    trace = MagicMock()
    slack, sheets, members, ack = (MagicMock() for _ in range(4))
    for name, collaborator in (
        ("slack", slack),
        ("sheets", sheets),
        ("members", members),
        ("ack", ack),
    ):
        trace.attach_mock(collaborator, name)

    worksheet_id = 161837744 if case["kind"] == "mention" else 987654321
    sheets.create_bigchat_sheet.return_value = worksheet_id
    sheets.get_url.return_value = (
        f"https://docs.google.com/spreadsheets/d/1FtKRO4/edit#gid={worksheet_id}"
    )
    sheets.append_row_if_absent.return_value = True
    members.find.return_value = create_sample_member()
    users = case.get("users")
    slack.get_emoji.return_value = (
        Reaction(name="gogo", users=users, count=len(users)) if users else None
    )

    failure = case.get("failure")
    if failure == "response_url":
        slack.send_thread_message.side_effect = SlackApiError(
            "boom", {"error": "not_in_channel"}
        )
        slack.send_response_url_message.side_effect = RuntimeError("응답 전송 실패")
    elif failure == "reaction":
        slack.get_emoji.side_effect = RuntimeError("반응 조회 실패")
    elif failure == "group":
        slack.send_thread_message.side_effect = [RuntimeError("일괄 안내 실패"), None]
    elif failure == "ephemeral":
        slack.send_message_only_visible_to_user.side_effect = [
            RuntimeError("신청 정보 안내 실패"),
            None,
        ]

    if case["kind"] == "mention":
        text = "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        if case.get("multiline"):
            text += "\n이번 빅챗 소개글입니다"
        event = create_sample_app_mention_event(text)
        run = CreateBigchatSheet(event, slack, sheets, members, "gogo").handle_mention
    else:
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )
        event = normalize_view_body(body)
        run = SubmitCreateBigchatModal(event, ack, slack, sheets, members, "gogo").run

    returned, raised = None, None
    try:
        returned = run()
    except Exception as error:
        raised = {"type": type(error).__name__, "message": str(error)}
    calls = [
        {"method": name, "args": list(args), "kwargs": kwargs}
        for name, args, kwargs in trace.mock_calls
    ]
    return json.loads(
        json.dumps(
            {"returned": returned, "raised": raised, "calls": calls}, ensure_ascii=False
        )
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_creation_matches_recorded_behavior(case):
    baseline = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert capture_behavior(case) == baseline[case["id"]]
