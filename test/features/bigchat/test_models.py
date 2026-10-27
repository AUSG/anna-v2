from datetime import datetime

import pytest

from features.bigchat.models import BigchatEvent, CreateBigchatCommand
from shared.time import KST

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"
EVENT = BigchatEvent(
    "AI 밋업",
    datetime(2026, 8, 20, 19, tzinfo=KST),
    datetime(2026, 8, 20, 21, tzinfo=KST),
)


@pytest.mark.parametrize("sheet_name", [SHEET_NAME, f"  {SHEET_NAME}  "])
def test_valid_command_keeps_the_original_title(sheet_name):
    command = CreateBigchatCommand.parse(sheet_name)

    assert command is not None
    assert command.sheet_name == sheet_name  # 안내문에 그대로 쓰이므로 공백도 보존
    assert command.event == EVENT


@pytest.mark.parametrize(
    "sheet_name",
    [
        "빅챗 23-07-31",  # 시간 없음 (구형식)
        "AI 밋업 2026-08-20 19:00~21:00",  # yyyy
        "AI 밋업 26-08-20 19:00-21:00",  # ~ 대신 -
        "26-08-20 19:00~21:00",  # 이름 없음
        "",
        "AI 밋업 26-02-30 19:00~21:00",  # 존재하지 않는 날짜
        "AI 밋업 26-08-20 25:00~26:00",  # 존재하지 않는 시각
        "AI 밋업 26-08-20 21:00~19:00",  # 종료가 시작보다 빠름
        "AI 밋업 26-08-20 19:00~19:00",  # 종료가 시작과 같음
    ],
)
def test_invalid_command_is_none(sheet_name):
    assert CreateBigchatCommand.parse(sheet_name) is None
