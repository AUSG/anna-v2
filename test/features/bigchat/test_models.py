import pytest

from features.bigchat.models import CreateBigchatCommand, InvalidBigchatName

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"


@pytest.mark.parametrize("sheet_name", [SHEET_NAME, f"  {SHEET_NAME}  "])
def test_valid_command_keeps_the_original_title(sheet_name):
    assert CreateBigchatCommand(sheet_name).sheet_name == sheet_name


def test_invalid_command_raises_domain_error():
    with pytest.raises(InvalidBigchatName):
        CreateBigchatCommand("빅챗 23-07-31")
