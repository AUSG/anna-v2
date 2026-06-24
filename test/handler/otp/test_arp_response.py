import unittest
from unittest.mock import MagicMock

from handler.otp.arp_response import ArpOtpResponse
from test.handler.bigchat.sample_data import create_sample_app_mention_event


class TestArpOtpResponse(unittest.TestCase):
    def test_run(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> otp")
        mock_slack_client = MagicMock()
        mock_otp = MagicMock()
        mock_otp.issue_login_url.return_value = "https://arp.ausg.me/auth/otp?code=test"
        sut = ArpOtpResponse(event, mock_slack_client, mock_otp)

        result = sut.handle_mention()

        mock_otp.issue_login_url.assert_called_once_with("UQJ8HQJG5")
        mock_slack_client.send_message_only_visible_to_user.assert_called_once()
        kwargs = mock_slack_client.send_message_only_visible_to_user.call_args.kwargs
        assert kwargs["user_id"] == "UQJ8HQJG5"
        assert kwargs["channel"] == "C03SZTDEDK3"
        assert kwargs["ts"] == "1689403771.805849"
        assert "10분" in kwargs["msg"]
        assert result is True

    def test_not_run_by_command_notfound(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> help")
        mock_slack_client = MagicMock()
        mock_otp = MagicMock()
        sut = ArpOtpResponse(event, mock_slack_client, mock_otp)

        result = sut.handle_mention()

        mock_otp.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_not_run_when_otp_is_not_exact_command(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> help otp")
        mock_slack_client = MagicMock()
        mock_otp = MagicMock()
        sut = ArpOtpResponse(event, mock_slack_client, mock_otp)

        result = sut.handle_mention()

        mock_otp.assert_not_called()
        mock_slack_client.assert_not_called()
        assert result is False

    def test_run_by_config_error(self):
        event = create_sample_app_mention_event("<@U01BN035Y6L> otp")
        mock_slack_client = MagicMock()
        mock_otp = MagicMock()
        mock_otp.issue_login_url.side_effect = ValueError()
        sut = ArpOtpResponse(event, mock_slack_client, mock_otp)

        result = sut.handle_mention()

        mock_slack_client.send_message.assert_called_once()
        assert result is False
