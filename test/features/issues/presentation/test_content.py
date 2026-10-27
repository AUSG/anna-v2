import pytest

from features.issues.models import Issue
from features.issues.presentation.content import (
    THREAD_CONTEXT_MAX_CHARS,
    build_issue_body,
    build_issue_footer,
    build_thread_context,
    issue_created_message,
    issue_failed_message,
)
from shared.slack_models import Message

ANNA_ID = "U01BN035Y6L"


def _message(user, text):
    return Message(
        ts="1689403100.222939",
        thread_ts="1689403100.222939",
        channel="C03SZTDEDK3",
        user=user,
        text=text,
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


@pytest.mark.parametrize(
    ("messages", "expected"),
    [
        pytest.param(
            [
                _message("U0", None),
                # 스레드 인용에서도 멘션 코드는 걷어낸다
                _message("U1", f" <@{ANNA_ID}> \n "),
                _message("U2", " 첫 줄\r\n  코드\u2028끝  "),
                _message("U3", " 🐍 "),
            ],
            "> **U2**: 첫 줄\r\n  코드\u2028끝\n>\n> **U3**: 🐍",
            id="inner-newlines",
        ),
        pytest.param([_message("", " ")], "", id="blank-without-user"),
        pytest.param([], "", id="empty-thread"),
        pytest.param(
            [
                _message("U0001", "어제 리마인더 두 번 왔는데 저만 그런가요?"),
                _message("U0002", f"저도요 <@{ANNA_ID}>"),
            ],
            "> **U0001**: 어제 리마인더 두 번 왔는데 저만 그런가요?\n>\n> **U0002**: 저도요",
            id="two-messages",
        ),
        pytest.param(
            [
                _message("U0", "제외"),
                _message("U1", "가" * 1489),
                _message("U2", "나" * 1489),
            ],
            "> **U1**: " + "가" * 1489 + "\n>\n> **U2**: " + "나" * 1489,
            id="exact-budget",
        ),
        pytest.param(
            [_message("U1", "가" * 1489), _message("U2", "나" * 1490)],
            "> **U2**: " + "나" * 1490,
            id="one-over-budget",
        ),
        pytest.param(
            [_message("U1", "이전 대화"), _message("U2", "🐍" * 3500)],
            "> **U2**: " + "🐍" * 3500,
            id="latest-oversize",
        ),
        pytest.param(
            [
                _message("U1", "짧은 과거"),
                _message("U2", "가" * 3000),
                _message("U3", "최신"),
            ],
            "> **U3**: 최신",
            id="stop-at-middle",
        ),
    ],
)
def test_thread_context_fills_from_the_latest_within_budget(messages, expected):
    assert THREAD_CONTEXT_MAX_CHARS == 3000
    assert build_thread_context(messages) == expected


@pytest.mark.parametrize(
    ("issue", "expected"),
    [
        (
            Issue(
                number=42,
                title="빅챗 리마인더가 두 번 와요",
                url="https://github.com/AUSG/anna-v2/issues/42",
            ),
            "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/42|#42 빅챗 리마인더가 두 번 와요>",
        ),
        # 제목의 <, > 가 그대로 나가면 슬랙 링크 표기가 깨진다
        (
            Issue(
                number=42,
                title="<script> 태그가 안 먹어요",
                url="https://github.com/AUSG/anna-v2/issues/42",
            ),
            "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/42|#42 &lt;script&gt; 태그가 안 먹어요>",
        ),
        (
            Issue(
                number=7,
                title="<script> | &lt; & > 🐍",
                url="https://github.com/AUSG/anna-v2/issues/7",
            ),
            "이슈 만들었어! <https://github.com/AUSG/anna-v2/issues/7|#7 &lt;script&gt; &#124; &lt; & &gt; 🐍>",
        ),
    ],
)
def test_issue_created_message_escapes_link_text(issue, expected):
    assert issue_created_message(issue) == expected


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (
            "깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!",
            ":blob-fearful: 이슈를 만들지 못했어. 깃허브에 연결하지 못했어. 잠시 뒤에 다시 시도해줘!",
        ),
        ("거절 <403>|🐍", ":blob-fearful: 이슈를 만들지 못했어. 거절 <403>|🐍"),
    ],
)
def test_issue_failed_message_keeps_reason_verbatim(reason, expected):
    assert issue_failed_message(reason) == expected
