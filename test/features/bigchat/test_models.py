from datetime import date, datetime

import pytest

from features.bigchat.calendar import KST, BigchatEvent
from features.bigchat.models import (
    CreateBigchatCommand,
    InvalidBigchatName,
    select_bigchats,
)

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"


@pytest.mark.parametrize("sheet_name", [SHEET_NAME, f"  {SHEET_NAME}  "])
def test_valid_command_keeps_the_original_title(sheet_name):
    assert CreateBigchatCommand(sheet_name).sheet_name == sheet_name


def test_invalid_command_raises_domain_error():
    with pytest.raises(InvalidBigchatName):
        CreateBigchatCommand("빅챗 23-07-31")


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


def test_select_bigchats_empty():
    assert select_bigchats([], date(2026, 8, 20)) == ([], [], [])
