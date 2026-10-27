"""빅챗 생성 응답 전문과 게이트웨이 호출 순서를 fixture와 비교한다.

trace 는 Runtime 계약(spec 을 건 MagicMock)의 경계에서 기록하므로, 계약에 없는 호출은
기록되기 전에 실패한다. fixture 를 다시 뜨려면 capture_behavior 를 case 별로 돌려 저장한다.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from slack_sdk.errors import SlackApiError

from features.bigchat.services.commands import parse_create_bigchat
from features.bigchat.slack import create_from_mention, submit_create_bigchat_modal
from shared.gateways import AppendOutcome
from shared.slack_events import MentionEvent, ViewSubmission
from shared.slack_models import Reaction
from test.fixtures.runtime import fake_runtime
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
    runtime = fake_runtime()
    slack, sheets, members = runtime.slack, runtime.sheets(), runtime.members()
    ack = MagicMock(name="ack")
    trace = MagicMock()
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
    sheets.append_row_if_absent.return_value = AppendOutcome.ADDED
    members.find.return_value = create_sample_member()
    users = case.get("users")
    slack.get_reaction.return_value = (
        Reaction(name="gogo", users=users, count=len(users)) if users else None
    )

    failure = case.get("failure")
    if failure == "response_url":
        slack.send_thread_message.side_effect = SlackApiError(
            "boom", {"error": "not_in_channel"}
        )
        slack.send_response_url_message.side_effect = RuntimeError("응답 전송 실패")
    elif failure == "reaction":
        slack.get_reaction.side_effect = RuntimeError("반응 조회 실패")
    elif failure == "group":
        # 첫 번째는 시트 링크 답글(성공), 두 번째가 일괄 등록 그룹 안내(실패)
        slack.send_thread_message.side_effect = [None, RuntimeError("일괄 안내 실패"), None]
    elif failure == "ephemeral":
        slack.send_ephemeral.side_effect = [RuntimeError("신청 정보 안내 실패"), None]

    if case["kind"] == "mention":
        text = "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        if case.get("multiline"):
            text += "\n이번 빅챗 소개글입니다"
        event = MentionEvent.from_payload(create_sample_app_mention_event(text))

        def run():
            return create_from_mention(
                parse_create_bigchat(event.text), event, slack, runtime
            )

    else:
        body = create_sample_view_submission_body(
            "AI 밋업", "2026-08-20", "19:00", "21:00"
        )
        submission = ViewSubmission.from_payload(body)

        def run():
            return submit_create_bigchat_modal(submission, ack, slack, runtime)

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
