import unittest
from unittest.mock import MagicMock

from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from test.handler.bigchat.sample_data import create_sample_app_mention_event


class TestCreateBigchatSheet(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event(
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 19:00~21:00"
        )
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.create_bigchat_sheet.assert_called_once_with(
            "AI 밋업 26-08-20 19:00~21:00"
        )
        mock_gs_client.get_url.assert_called_once()
        mock_slack_client.send_message.assert_called_once()
        assert result is True
        assert (
            "새로운 빅챗, 등록 완료!" in mock_slack_client.send_message.call_args.kwargs["msg"]
        )

    def test_not_run_by_command_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L>빅챗 23-07-31")
        mock_slack_client = MagicMock()
        mock_gs_client = MagicMock()
        sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

        result = sut.handle_mention()

        mock_gs_client.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_rejected_by_invalid_format(self):
        for text in [
            "<@U01BN035Y6L> 새로운 빅챗 \n\n\n\n",  # 이름 없음
            "<@U01BN035Y6L> 새로운 빅챗 빅챗 23-07-31",  # 시간 없음 (구형식)
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-02-30 19:00~21:00",  # 존재하지 않는 날짜
            "<@U01BN035Y6L> 새로운 빅챗 AI 밋업 26-08-20 21:00~19:00",  # 종료가 시작보다 빠름
        ]:
            event = create_sample_app_mention_event(text)
            mock_slack_client = MagicMock()
            mock_gs_client = MagicMock()
            sut = CreateBigchatSheet(event, mock_slack_client, mock_gs_client)

            result = sut.handle_mention()

            mock_gs_client.create_bigchat_sheet.assert_not_called()
            mock_slack_client.send_message.assert_not_called()
            mock_slack_client.send_message_only_visible_to_user.assert_called_once()
            assert result is False
            assert (
                "형식이 올바르지 않아서 빅챗을 만들지 않았어"
                in mock_slack_client.send_message_only_visible_to_user.call_args.kwargs[
                    "msg"
                ]
            )
