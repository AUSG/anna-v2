"""명령 구문·별칭·우선순위와 질문 추출 규칙을 검증한다."""

import pytest

from features.bigchat.services.commands import CreateBigchat, Reminder
from features.bot_commands.models import Empty, Help, Shuffle
from features.issues.models import CreateIssue
from features.questions.models import Question
from features.questions.services.commands import extract_question
from slack_router import parse_mention

ANNA_ID = "UANNA"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@UANNA> Q) 새로운 빅챗", Question("새로운 빅챗", explicit=True)),
        ("<@UANNA> 앞 문장 q) 뒤의 질문", Question("뒤의 질문", explicit=True)),
        ("<@UANNA> q)   <@UOTHER>", Question("", explicit=True)),
        ("<@UANNA> shuffle <@U1> <@U2>", Shuffle(("U1", "U2"))),
        ("<@UANNA> SHUFFLE", Shuffle(())),
        ("<@UANNA> 섞어줘", Shuffle(())),
        ("<@UANNA> 빅챗 리마인더", Reminder("usage")),
        ("<@UANNA> 새로운 빅챗", CreateBigchat("")),
        ("<@UANNA> 새 이슈 버그", CreateIssue("버그")),
        ("<@UANNA> 이슈 만들어줘 버그", CreateIssue("버그")),
        ("<@UANNA> 이슈 등록해줘 버그", CreateIssue("버그")),
        ("<@UANNA> 이슈 파줘 버그", CreateIssue("버그")),
        ("<@UANNA> 이슈 따줘 버그", CreateIssue("버그")),
        ("<@UANNA> 새로운 이슈", CreateIssue("")),
        ("<@UANNA> help", Help()),
        ("<@UANNA> 도움말 보여줘", Help()),
        ("<@UANNA> helpful", Help()),  # 부분 문자열로 판별한다
        ("<@UANNA> HELP", Question("HELP", explicit=False)),  # help는 대소문자를 구분한다
        ("<@UANNA> <@UOTHER> 안녕", Question("안녕", explicit=False)),
        ("<@UANNA> <@UOTHER> \n\t", Empty()),
        ("", Empty()),
        ("   ", Empty()),
    ],
)
def test_classifies_mentions(text, expected):
    command = parse_mention(text, ANNA_ID)
    assert type(command) is type(expected)
    assert command == expected


@pytest.mark.parametrize(
    ("text", "expected_type"),
    [
        ("q) shuffle 빅챗 리마인더 새로운 빅챗 새로운 이슈 help", Question),
        ("shuffle 빅챗 리마인더 새로운 빅챗 새로운 이슈 help", Shuffle),
        ("빅챗 리마인더 새로운 빅챗 새로운 이슈 help", Reminder),
        ("새로운 빅챗 새로운 이슈 help", CreateBigchat),
        ("새로운 이슈 help 기능이 고장났어요", CreateIssue),
    ],
)
def test_preserves_command_priority(text, expected_type):
    assert type(parse_mention(text, ANNA_ID)) is expected_type


@pytest.mark.parametrize(
    ("text", "require_prefix", "expected"),
    [
        ("<@UANNA> q) 질문\n추가 설명", True, "질문\n추가 설명"),
        ("<@UANNA> Q) <@UOTHER> 질문", True, "질문"),
        ("<@UANNA> q) <@UOTHER>", True, ""),
        ("<@UANNA> 일반 질문", True, ""),
        ("<@UANNA> 일반 질문", False, "일반 질문"),
        ("<@UANNA> q) 질문", False, "질문"),
        ("<@UANNA>", False, ""),
    ],
)
def test_extracts_questions_with_existing_rules(text, require_prefix, expected):
    assert extract_question(text, require_prefix=require_prefix) == expected


def test_shuffle_excludes_anna_but_keeps_order_and_duplicates():
    command = parse_mention("<@UANNA> shuffle <@U2> <@UANNA> <@U1> <@U2>", ANNA_ID)
    assert command == Shuffle(("U2", "U1", "U2"))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@UANNA> 빅챗 리마인더", Reminder("usage")),
        ("<@UANNA> 빅챗 리마인더 아무말", Reminder("usage")),
        ("<@UANNA> 빅챗 리마인더 테스트", Reminder("test", ())),
        ("<@UANNA> 빅챗 리마인더 테스트 <@U1> <@UANNA> <@U2>", Reminder("test", ("U1", "U2"))),
        ("<@UANNA> 빅챗 리마인더 지금 전원 발송", Reminder("broadcast")),
        # 전원 발송 문구가 있으면 테스트 대상 멘션이 있어도 전원 발송이다
        ("<@UANNA> 빅챗 리마인더 테스트 지금 전원 발송 <@U1>", Reminder("broadcast")),
    ],
)
def test_reminder_modes(text, expected):
    assert parse_mention(text, ANNA_ID) == expected


@pytest.mark.parametrize(
    ("text", "sheet_name"),
    [
        ("<@UANNA> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00", "AI 밋업 26-08-20 19:00~21:00"),
        (
            "<@UANNA> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00\n둘째 줄은 무시",
            "AI 밋업 26-08-20 19:00~21:00",
        ),
        (
            "<@UANNA> 새로운 빅챗 <@UOTHER> 이름 26-08-20 19:00~21:00",
            "이름 26-08-20 19:00~21:00",
        ),
        ("새로운 빅챗 이름 26-08-20 19:00~21:00 <@UANNA>", "이름 26-08-20 19:00~21:00"),
        ("<@UANNA> 새로운 빅챗", ""),
    ],
)
def test_create_bigchat_takes_only_the_first_line_after_trigger(text, sheet_name):
    assert parse_mention(text, ANNA_ID) == CreateBigchat(sheet_name)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@UANNA> 새로운 이슈 제목", CreateIssue("제목", "")),
        ("<@UANNA> 새로운 이슈 제목\n본문 첫 줄\n본문 둘째 줄", CreateIssue("제목", "본문 첫 줄\n본문 둘째 줄")),
        ("<@UANNA> 이슈 만들어줄래? 제목", CreateIssue("제목", "")),
        ("<@UANNA> 이슈 만들어줘: 제목", CreateIssue("제목", "")),
        ("새로운 이슈 제목 <@UANNA>", CreateIssue("제목", "")),
        ("<@UANNA> 새로운 이슈", CreateIssue("", "")),
        # 제목 줄이 비어 있으면 다음 줄이 제목으로 올라온다
        ("<@UANNA> 새로운 이슈 \n본문만", CreateIssue("본문만", "")),
    ],
)
def test_create_issue_splits_title_and_body(text, expected):
    assert parse_mention(text, ANNA_ID) == expected


def test_create_issue_truncates_long_titles():
    command = parse_mention("<@UANNA> 새로운 이슈 " + "가" * 200, ANNA_ID)
    assert isinstance(command, CreateIssue)
    assert len(command.title) == 120
    assert command.title.endswith("…")
