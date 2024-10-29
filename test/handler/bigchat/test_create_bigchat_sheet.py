import unittest
from unittest.mock import MagicMock

from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from test.handler.bigchat.sample_data import create_sample_app_mention_event


class TestCreateBigchatSheet(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.create_bigchat_sheet.assert_called_once()
        mock_gs_client.get_url.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert "새로운 빅챗, 등록 완료!" in mock_slack_client.send_message.call_args.kwargs["msg"]

    def test_not_run_by_command_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_not_run_by_sheet_name_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> 새로운 빅챗 \n\n\n\n")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.assert_not_called()
        mock_slack_client.send_message.assert_called_once()
        assert result is False
        assert "시트 이름이 입력되지 않았어. 다시 입력해줘!" in mock_slack_client.send_message.call_args.kwargs["msg"]
