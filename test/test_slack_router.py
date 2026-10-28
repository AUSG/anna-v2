"""명령 구문과 별칭, 우선순위, 질문 추출 규칙을 검증한다."""

import pytest

from slack_router import classify_mention, extract_question, matches_mention


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<@UANNA> Q) 새로운 빅챗", "explicit_question"),
        ("<@UANNA> 앞 문장 q) 뒤의 질문", "explicit_question"),
        ("<@UANNA> q)   <@UOTHER>", "explicit_question"),
        ("<@UANNA> shuffle <@U1> <@U2>", "shuffle"),
        ("<@UANNA> SHUFFLE", "shuffle"),
        ("<@UANNA> 섞어줘", "shuffle"),
        ("<@UANNA> 빅챗 리마인더", "reminder"),
        ("<@UANNA> 새로운 빅챗", "create_bigchat"),
        ("<@UANNA> 새 이슈 버그", "create_issue"),
        ("<@UANNA> 이슈 만들어줘 버그", "create_issue"),
        ("<@UANNA> 이슈 등록해줘 버그", "create_issue"),
        ("<@UANNA> 이슈 파줘 버그", "create_issue"),
        ("<@UANNA> 이슈 따줘 버그", "create_issue"),
        ("<@UANNA> 새로운 이슈", "create_issue"),
        ("<@UANNA> help", "help"),
        ("<@UANNA> 도움말 보여줘", "help"),
        ("<@UANNA> helpful", "help"),  # 기존 부분 문자열 판별 유지
        ("<@UANNA> HELP", "question"),  # help는 기존에도 대소문자를 구분한다
        ("<@UANNA> <@UOTHER> 안녕", "question"),
        ("<@UANNA> <@UOTHER> \n\t", "empty"),
        ("", "empty"),
        ("   ", "empty"),
    ],
)
def test_classifies_mentions(text, expected):
    assert classify_mention(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "q) shuffle 빅챗 리마인더 새로운 빅챗 새로운 이슈 help",
            "explicit_question",
        ),
        ("shuffle 빅챗 리마인더 새로운 빅챗 새로운 이슈 help", "shuffle"),
        ("빅챗 리마인더 새로운 빅챗 새로운 이슈 help", "reminder"),
        ("새로운 빅챗 새로운 이슈 help", "create_bigchat"),
        ("새로운 이슈 help 기능이 고장났어요", "create_issue"),
    ],
)
def test_preserves_command_priority(text, expected):
    assert classify_mention(text) == expected


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


def test_empty_match_excludes_nonempty_questions():
    assert matches_mention("empty", "<@UANNA>") is True
    assert matches_mention("empty", "<@UANNA> 질문") is False
