import pytest

from features.issues.presentation.content import (
    build_issue_body,
    build_issue_footer,
    parse_issue_command,
)


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
        ("새로운 이슈 제목\u2028본문\u2029끝", ("제목\u2028본문\u2029끝", "")),
        ("새로운 이슈 제목\v본문\f끝", ("제목\v본문\f끝", "")),
        ("\u3000새로운 이슈\u00a0제목\u3000\n\u00a0본문\u3000", ("제목", "본문")),
        ("새로운 이슈 🐍 e\u0301 한글  제목\n  본문 🧪  ", ("🐍 e\u0301 한글  제목", "본문 🧪")),
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
    assert parse_issue_command(text) == expected


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("가" * 119, "가" * 119),
        ("가" * 120, "가" * 120),
        ("가" * 121, "가" * 119 + "…"),
        ("가" * 300, "가" * 119 + "…"),
        ("가" * 118 + " \t나", "가" * 118 + "…"),
        ("🐍" * 121, "🐍" * 119 + "…"),
        ("e\u0301" * 61, "e\u0301" * 59 + "e…"),
        ("👩‍💻" * 41, "👩‍💻" * 39 + "👩‍…"),
        ("가" * 119 + "<@U1>나", "가" * 119 + "나"),
    ],
)
def test_title_truncation_counts_code_points_and_strips_cut_whitespace(title, expected):
    assert parse_issue_command("새로운 이슈 " + title + "\n본문") == (expected, "본문")


def test_command_body_is_not_truncated_with_the_title():
    assert parse_issue_command("새로운 이슈 제목\n" + "긴 본문\n" * 1000) == (
        "제목",
        "긴 본문\n" * 999 + "긴 본문",
    )


@pytest.mark.parametrize(
    ("body", "thread_context", "footer", "expected"),
    [
        ("", "", "---\n푸터", "---\n푸터"),
        ("요청 본문", "", "---\n푸터", "요청 본문\n\n---\n푸터"),
        (
            "",
            "> **U1**: 대화",
            "---\n푸터",
            "### 슬랙 스레드\n\n> **U1**: 대화\n\n---\n푸터",
        ),
        (
            "요청 본문\n  코드",
            "> **U1**: 첫 대화\n>\n> **U2**: 다음 대화",
            "---\n슬랙에서 `U3` 가 안나에게 요청해서 만들어진 이슈야.\n원문: https://example.test/p1",
            "요청 본문\n  코드\n\n### 슬랙 스레드\n\n> **U1**: 첫 대화\n>\n> **U2**: 다음 대화"
            "\n\n---\n슬랙에서 `U3` 가 안나에게 요청해서 만들어진 이슈야.\n원문: https://example.test/p1",
        ),
        (
            " \n본문\r\n  ",
            " \n> 🐍\u2028  ",
            "\n---\n ",
            " \n본문\r\n  \n\n### 슬랙 스레드\n\n \n> 🐍\u2028  \n\n\n---\n ",
        ),
        (" ", "\t", " ", " \n\n### 슬랙 스레드\n\n\t\n\n "),
        ("", "", "", ""),
        ("본문", "", "", "본문\n\n"),
        ("", "> 대화", "", "### 슬랙 스레드\n\n> 대화\n\n"),
    ],
)
def test_body_assembly_preserves_order_and_exact_whitespace(
    body, thread_context, footer, expected
):
    assert build_issue_body(body, thread_context, footer) == expected


@pytest.mark.parametrize(
    ("user", "permalink", "expected"),
    [
        ("U1", "", "---\n슬랙에서 `U1` 가 안나에게 요청해서 만들어진 이슈야."),
        (
            "U1",
            "https://example.test/p1?a=1&b=2",
            "---\n슬랙에서 `U1` 가 안나에게 요청해서 만들어진 이슈야."
            "\n원문: https://example.test/p1?a=1&b=2",
        ),
        (None, "", "---\n슬랙에서 `None` 가 안나에게 요청해서 만들어진 이슈야."),
        ("", "", "---\n슬랙에서 `` 가 안나에게 요청해서 만들어진 이슈야."),
        (
            "한글 🐍 <@U1>|`",
            " \nhttps://example.test/p1\t ",
            "---\n슬랙에서 `한글 🐍 <@U1>|`` 가 안나에게 요청해서 만들어진 이슈야."
            "\n원문:  \nhttps://example.test/p1\t ",
        ),
    ],
)
def test_footer_preserves_user_and_permalink_without_normalization(
    user, permalink, expected
):
    assert build_issue_footer(user, permalink) == expected
