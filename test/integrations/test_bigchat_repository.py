from unittest.mock import MagicMock

import pytest

from features.bigchat.models import BigchatCreated, CreateBigchatCommand
from features.bigchat.services.creation import create_bigchat
from integrations.bigchat_repository import SpreadsheetBigchatRepository


def test_creation_service_and_spreadsheet_adapter_preserve_title_and_result():
    client = MagicMock()
    client.create_bigchat_sheet.return_value = 123
    client.get_url.return_value = "https://sheets.test/#gid=123"
    title = "  AI 밋업 26-08-20 19:00~21:00  "
    result = create_bigchat(
        CreateBigchatCommand(title), SpreadsheetBigchatRepository(client)
    )
    assert result == BigchatCreated(123, title, "https://sheets.test/#gid=123")
    client.create_bigchat_sheet.assert_called_once_with(title)
    client.get_url.assert_called_once_with(123)


def test_creation_service_accepts_a_repository_without_any_sdk():
    class InMemoryBigchats:
        def create(self, sheet_name):
            return BigchatCreated(1, sheet_name, "memory:1")

    command = CreateBigchatCommand("빅챗 26-08-20 19:00~21:00")
    assert create_bigchat(command, InMemoryBigchats()) == BigchatCreated(
        1, command.sheet_name, "memory:1"
    )


def test_adapter_preserves_original_failure_and_does_not_build_a_url():
    client = MagicMock()
    failure = RuntimeError("write failed")
    client.create_bigchat_sheet.side_effect = failure
    with pytest.raises(RuntimeError) as caught:
        SpreadsheetBigchatRepository(client).create("title")
    assert caught.value is failure
    client.get_url.assert_not_called()
