"""언어 중립 계약 fixture (test/fixtures/contracts/*.json) 를 현재 구현으로 검증한다.

입력과 기대 출력만 JSON 으로 적어 두어, 다른 언어로 재작성한 구현도 같은 파일로 검증할 수 있다.
새 케이스는 JSON 에 추가하고 기대값은 손으로 확인해서 적는다.
"""

import dataclasses
import json
from datetime import date
from pathlib import Path

import pytest

from features.bigchat.models import ReminderResult, parse_sheet_name
from features.bigchat.presentation.calendar import to_gcal_link_truncated, to_ics
from features.bigchat.presentation.reminders import build_reminder, build_report
from features.bigchat.services.reminder_policy import applicant_email, select_bigchats
from features.bigchat.services.sheet_link import extract_worksheet_id
from features.issues.presentation.content import build_issue_body, build_issue_footer
from features.issues.services.commands import parse_issue_command
from features.questions.models import ChatFailure, ChatResult, Source
from features.questions.presentation.answers import render_parts
from features.questions.services.commands import extract_question
from slack_router import parse_mention

CONTRACTS = Path(__file__).parent / "fixtures" / "contracts"


def load(name):
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def cases(name, key=None):
    data = load(name)
    return data[key] if key else data


def as_json(value):
    """dataclass 를 JSON 과 비교 가능한 형태로 (tuple 은 list 로)."""
    return json.loads(json.dumps(dataclasses.asdict(value), ensure_ascii=False))


@pytest.mark.parametrize(
    "case", cases("mention_routing.json"), ids=lambda c: c["text"][:40]
)
def test_mention_routing(case):
    command = parse_mention(case["text"], case["anna_id"])
    assert {"command": type(command).__name__, **as_json(command)} == case["expected"]


@pytest.mark.parametrize(
    "case", cases("sheet_names.json"), ids=lambda c: c["sheet_name"]
)
def test_sheet_names(case):
    event = parse_sheet_name(case["sheet_name"])
    actual = (
        None
        if event is None
        else {
            "name": event.name,
            "start": event.start.isoformat(),
            "end": event.end.isoformat(),
        }
    )
    assert actual == case["expected"]


@pytest.mark.parametrize(
    "case", cases("issue_commands.json"), ids=lambda c: c["text"][:30]
)
def test_issue_commands(case):
    assert as_json(parse_issue_command(case["text"])) == case["expected"]


@pytest.mark.parametrize(
    "case", cases("question_extraction.json"), ids=lambda c: c["text"][:30]
)
def test_question_extraction(case):
    assert (
        extract_question(case["text"], require_prefix=case["require_prefix"])
        == case["expected"]
    )


def _chat_result(raw):
    if "failure" in raw:
        return ChatFailure(raw["failure"])
    return ChatResult(
        answer=raw["answer"],
        sources=[Source(**source) for source in raw["sources"]],
        timing=raw["timing"],
        status=raw["status"],
        citations=raw["citations"],
        trace_id=raw["trace_id"],
    )


@pytest.mark.parametrize("case", cases("answer_rendering.json"), ids=lambda c: c["id"])
def test_answer_rendering(case):
    answer, sources = render_parts(_chat_result(case["result"]))
    assert {"answer": answer, "sources": sources} == case["expected"]


@pytest.mark.parametrize(
    "case", cases("calendar.json", "gcal"), ids=lambda c: str(len(c["details"]))
)
def test_gcal_links(case):
    event = parse_sheet_name(case["sheet_name"])
    assert (
        to_gcal_link_truncated(event, case["details"], limit=case["limit"])
        == case["expected_gcal_url"]
    )
    assert len(case["expected_gcal_url"]) <= case["limit"]


def test_ics():
    case = cases("calendar.json", "ics")
    ics = to_ics(
        parse_sheet_name(case["sheet_name"]),
        uid=case["uid"],
        description=case["description"],
    )
    lines = [line for line in ics.split("\r\n") if not line.startswith("DTSTAMP:")]
    assert lines == case["expected_lines_without_dtstamp"]


@pytest.mark.parametrize(
    "case", cases("reminders.json", "reminder_messages"), ids=lambda c: c["sheet_name"]
)
def test_reminder_messages(case):
    assert build_reminder(parse_sheet_name(case["sheet_name"])) == case["expected"]


@pytest.mark.parametrize(
    "case", cases("reminders.json", "reports"), ids=lambda c: str(c["targets"])
)
def test_reminder_reports(case):
    raw = dict(case["result"])
    raw["target_date"] = date.fromisoformat(raw["target_date"])
    assert build_report(ReminderResult(**raw), case["targets"]) == case["expected"]


def test_select_bigchats():
    case = cases("reminders.json", "select_bigchats")
    matched, parsed, ignored = select_bigchats(
        [tuple(w) for w in case["worksheets"]], date.fromisoformat(case["target_date"])
    )
    assert {
        "matched_worksheet_ids": [worksheet_id for worksheet_id, _ in matched],
        "parsed": parsed,
        "ignored": ignored,
    } == case["expected"]


@pytest.mark.parametrize(
    "case", cases("reminders.json", "applicant_emails"), ids=lambda c: str(c["row"])
)
def test_applicant_emails(case):
    assert applicant_email(case["row"]) == case["expected"]


@pytest.mark.parametrize(
    "case", cases("reminders.json", "sheet_links"), ids=lambda c: str(c["expected"])
)
def test_sheet_links(case):
    assert extract_worksheet_id(case["texts"]) == case["expected"]


@pytest.mark.parametrize(
    "case", cases("issue_body.json"), ids=lambda c: c["body"] or "(no body)"
)
def test_issue_body(case):
    footer = build_issue_footer(case["user"], case["permalink"])
    assert (
        build_issue_body(case["body"], case["thread_context"], footer)
        == case["expected"]
    )
