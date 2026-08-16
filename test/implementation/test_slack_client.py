import unittest
from unittest.mock import MagicMock

from implementation.slack_client import SlackClient


class TestSendDirectMessage(unittest.TestCase):
    def test_posts_to_user_id_as_channel(self):
        mock_web_client = MagicMock()
        # 스케줄 발송 컨텍스트에는 bolt 의 say 가 없다
        sut = SlackClient(say=None, web_client=mock_web_client)

        sut.send_direct_message(user_id="U0001", msg="내일 만나!")

        mock_web_client.chat_postMessage.assert_called_once_with(
            channel="U0001", text="내일 만나!"
        )
