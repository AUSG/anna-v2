import pytest

from features.issues.models import CreateIssue
from features.issues.services.commands import (
    MAX_TITLE_LEN,
    is_create_issue,
    parse_issue_command,
)

ANNA_ID = "U01BN035Y6L"


@pytest.mark.parametrize(
    "text",
    [
        f"<@{ANNA_ID}> 새로운 이슈 리마인더가 두 번 와요",
        f"<@{ANNA_ID}> 새 이슈 리마인더가 두 번 와요",
        f"<@{ANNA_ID}> 이슈 만들어줘 리마인더가 두 번 와요",
        f"<@{ANNA_ID}> 이슈 등록해줘 리마인더가 두 번 와요",
        f"<@{ANNA_ID}> 이슈 파줘 리마인더가 두 번 와요",
    ],
)
def test_trigger_phrases_are_recognized(text):
    assert is_create_issue(text)


@pytest.mark.parametrize(
    "text",
    [
        f"<@{ANNA_ID}> 안녕",
        # 이슈 이야기를 한다고 다 이슈를 만들면 곤란하다
        f"<@{ANNA_ID}> 그 이슈 어떻게 됐어?",
        f"<@{ANNA_ID}> 이슈 파악해줘",
        f"<@{ANNA_ID}> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00",
    ],
)
def test_non_trigger_phrases_are_not_recognized(text):
    assert not is_create_issue(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@U01BN035Y6L> 새로운 이슈 제목", ("제목", "")),
        ("<@U1> 새 이슈 제목", ("제목", "")),
        ("<@U1> 새이슈 제목", ("제목", "")),
        ("<@U1> 이슈 만들어줘 제목", ("제목", "")),
        ("<@U1> 이슈 만들어줄래? 제목", ("제목", "")),
        ("<@U1> 이슈 만들어줘: 제목", ("제목", "")),
        ("<@U1> 이슈 만들자 제목", ("제목", "")),
        ("<@U1> 이슈 등록해주세요 제목", ("제목", "")),
        ("<@U1> 이슈 생성해줘 제목", ("제목", "")),
        ("<@U1> 이슈 파줘 제목", ("제목", "")),
        ("<@U1> 이슈 따주세요 제목", ("제목", "")),
        ("앞의 설명 <@U1> 새로운 이슈 제목", ("제목", "")),
        ("새로운\t이슈\t?!.,:;~ \t 제목  \n  본문  \n", ("제목", "본문")),
        ("새로운 이슈 제목 <@U1>\n본문 <@U2> 끝", ("제목", "본문  끝")),
        ("새로운 이슈 제<@U1>목", ("제목", "")),
        ("새로운 이슈 제목 <@u1> <@U_1>", ("제목 <@u1> <@U_1>", "")),
        ("새로운 이슈 제목\n\n  첫 줄\n\t코드  \n끝  ", ("제목", "첫 줄\n\t코드  \n끝")),
        ("새로운 이슈 제목\r\n본문\r\n  다음 줄\r\n", ("제목", "본문\r\n  다음 줄")),
        ("새로운 이슈 제목\r본문", ("제목\r본문", "")),
        ("새로운 이슈 제목 본문 끝", ("제목 본문 끝", "")),
        ("새로운 이슈 제목\v본문\f끝", ("제목\v본문\f끝", "")),
        ("　새로운 이슈 제목　\n 본문　", ("제목", "본문")),
        ("새로운 이슈 🐍 é 한글  제목\n  본문 🧪  ", ("🐍 é 한글  제목", "본문 🧪")),
        ("새로운 이슈 <script> a|b & c", ("<script> a|b & c", "")),
        ("새로운 이슈 !?제목!?\n:본문;", ("제목!?", ":본문;")),
        ("새로운 이슈 제목 새로운 이슈 둘", ("제목 새로운 이슈 둘", "")),
        ("새로운 이슈\n제목\n본문", ("제목", "본문")),
        ("새로운 이슈 ?\n본문만 있음", ("", "본문만 있음")),
        ("새로운 이슈 ?\r\n본문만 있음", ("", "본문만 있음")),
        ("새로운 이슈", ("", "")),
        ("새로운 이슈 <@U1> ?!.,:;~\t ", ("", "")),
        ("<@U1> 이슈 만들어줘\n \t", ("", "")),
        ("", ("", "")),
        ("<@U1>\t", ("", "")),
        ("트리거 없는 제목\n본문", ("트리거 없는 제목", "본문")),
        ("이슈 파악해줘", ("이슈 파악해줘", "")),
    ],
)
def test_parse_issue_command(text, expected):
    assert parse_issue_command(text) == CreateIssue(*expected)


@pytest.mark.parametrize(
    ("text", "title"),
    [
        # "이슈 만들어줄래? 제목" 처럼 어미 뒤에 남는 문장부호를 턴다
        (f"<@{ANNA_ID}> 이슈 만들어줄래? 리마인더가 두 번 와요", "리마인더가 두 번 와요"),
        (f"<@{ANNA_ID}> 이슈 만들어줘: 리마인더가 두 번 와요", "리마인더가 두 번 와요"),
        (f"<@{ANNA_ID}> 새로운 이슈 빅챗 리마인더가 두 번 와요", "빅챗 리마인더가 두 번 와요"),
        (f"<@{ANNA_ID}> 새로운 이슈 " + "가" * 300, "가" * 119 + "…"),
    ],
)
def test_punctuation_after_trigger_and_long_titles(text, title):
    assert parse_issue_command(text) == CreateIssue(title, "")


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("가" * 119, "가" * 119),
        ("가" * 120, "가" * 120),
        ("가" * 121, "가" * 119 + "…"),
        ("가" * 300, "가" * 119 + "…"),
        ("가" * 118 + " \t나", "가" * 118 + "…"),
        ("🐍" * 121, "🐍" * 119 + "…"),
        ("é" * 61, "é" * 59 + "e…"),
        ("👩‍💻" * 41, "👩‍💻" * 39 + "👩‍…"),
        ("가" * 119 + "<@U1>나", "가" * 119 + "나"),
    ],
)
def test_title_truncation_counts_code_points_and_strips_cut_whitespace(title, expected):
    assert MAX_TITLE_LEN == 120
    assert parse_issue_command("새로운 이슈 " + title + "\n본문") == CreateIssue(
        expected, "본문"
    )


def test_command_body_is_not_truncated_with_the_title():
    assert parse_issue_command("새로운 이슈 제목\n" + "긴 본문\n" * 1000) == CreateIssue(
        "제목", "긴 본문\n" * 999 + "긴 본문"
    )


def test_empty_title_is_the_usage_signal():
    command = parse_issue_command(f"<@{ANNA_ID}> 이슈 만들어줘")
    assert command == CreateIssue("", "")
    assert not command.title
