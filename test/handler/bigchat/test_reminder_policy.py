from datetime import date, datetime

import pytest

from handler.bigchat.reminder_policy import applicant_email, select_bigchats
from util.bigchat_event import KST, BigchatEvent


def test_select_bigchats_preserves_sheet_order_and_scan_details():
    worksheets = [
        (9, "MEMBERS_INFO"),
        (4, " 저녁 빅챗 26-08-20 19:00~21:00 "),
        (3, "모레 빅챗 26-08-21 10:00~12:00"),
        (4, "오전 빅챗 26-08-20 10:00~12:00"),
        (5, "빅챗 23-07-31"),
    ]

    matched, parsed, ignored = select_bigchats(worksheets, date(2026, 8, 20))

    assert matched == [
        (
            4,
            BigchatEvent(
                "저녁 빅챗",
                datetime(2026, 8, 20, 19, tzinfo=KST),
                datetime(2026, 8, 20, 21, tzinfo=KST),
            ),
        ),
        (
            4,
            BigchatEvent(
                "오전 빅챗",
                datetime(2026, 8, 20, 10, tzinfo=KST),
                datetime(2026, 8, 20, 12, tzinfo=KST),
            ),
        ),
    ]
    assert parsed == [
        "' 저녁 빅챗 26-08-20 19:00~21:00 ' -> starts 2026-08-20",
        "'모레 빅챗 26-08-21 10:00~12:00' -> starts 2026-08-21",
        "'오전 빅챗 26-08-20 10:00~12:00' -> starts 2026-08-20",
    ]
    assert ignored == ["MEMBERS_INFO", "빅챗 23-07-31"]
    assert worksheets[1] == (4, " 저녁 빅챗 26-08-20 19:00~21:00 ")


def test_select_bigchats_empty():
    assert select_bigchats([], date(2026, 8, 20)) == ([], [], [])


@pytest.mark.parametrize(
    "title",
    [
        "",
        "빅챗 26-02-30 19:00~21:00",
        "빅챗 26-08-20 25:00~26:00",
        "빅챗 26-08-20 21:00~19:00",
        "빅챗 26-08-20 19:00~19:00",
        "줄\n바꿈 26-08-20 19:00~21:00",
    ],
)
def test_select_bigchats_keeps_invalid_titles_in_ignored(title):
    assert select_bigchats([(1, title)], date(2026, 8, 20)) == ([], [], [title])


@pytest.mark.parametrize("title", [None, 123])
def test_select_bigchats_does_not_swallow_invalid_title_types(title):
    with pytest.raises(AttributeError):
        select_bigchats([(1, title)], date(2026, 8, 20))


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ([], None),
        (["", " \t", "이메일"], None),
        (["김철수", "@drama&company", " Chulsoo@Example.com "], "chulsoo@example.com"),
        (["First@Example.com", "second@example.com"], "first@example.com"),
        (["not an@email.com", "good@example.com"], "good@example.com"),
        (["a@b", "a@b.c", "c@d.e"], "a@b.c"),
        (["두번째@EXAMPLE.COM"], "두번째@example.com"),
        (["\u00a0İ@EXAMPLE.COM\u00a0"], "i\u0307@example.com"),
        (["a@@b.c"], "a@@b.c"),
        (["first@example.com", None], "first@example.com"),
    ],
)
def test_applicant_email_uses_only_the_first_matching_cell(row, expected):
    before = list(row)
    assert applicant_email(row) == expected
    assert row == before


@pytest.mark.parametrize("cell", [None, 17])
def test_applicant_email_keeps_invalid_cell_errors(cell):
    with pytest.raises(AttributeError):
        applicant_email(["not email", cell, "valid@example.com"])


def test_applicant_email_keeps_invalid_row_error():
    with pytest.raises(TypeError):
        applicant_email(None)
