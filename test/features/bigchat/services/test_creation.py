"""시트 생성 서비스. 사전 반응자 일괄 등록은 features/bigchat/slack.py 의 backfill_early_reactions 가 맡는다."""

from unittest.mock import MagicMock

import pytest

from features.bigchat.models import BigchatCreated, CreateBigchatCommand
from features.bigchat.services.creation import create_bigchat
from shared.gateways import SheetsGateway

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"
WORKSHEET_ID = 161837744
SHEET_URL = f"https://docs.google.com/spreadsheets/d/a/edit#gid={WORKSHEET_ID}"


@pytest.fixture
def sheets():
    gateway = MagicMock(spec=SheetsGateway)
    gateway.create_bigchat_sheet.return_value = WORKSHEET_ID
    gateway.get_url.return_value = SHEET_URL
    return gateway


@pytest.mark.parametrize("sheet_name", [SHEET_NAME, f"  {SHEET_NAME}  "])
def test_creates_sheet_with_the_original_title_and_returns_its_url(sheets, sheet_name):
    created = create_bigchat(CreateBigchatCommand.parse(sheet_name), sheets)

    assert created == BigchatCreated(
        worksheet_id=WORKSHEET_ID, sheet_name=sheet_name, sheet_url=SHEET_URL
    )
    sheets.create_bigchat_sheet.assert_called_once_with(sheet_name)
    sheets.get_url.assert_called_once_with(WORKSHEET_ID)


def test_sheet_creation_failure_is_not_swallowed(sheets):
    sheets.create_bigchat_sheet.side_effect = RuntimeError("quota")

    with pytest.raises(RuntimeError, match="quota"):
        create_bigchat(CreateBigchatCommand.parse(SHEET_NAME), sheets)

    sheets.get_url.assert_not_called()
