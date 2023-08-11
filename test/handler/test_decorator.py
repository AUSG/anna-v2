import unittest
from unittest.mock import MagicMock

from handler.decorator import loading_emoji_while_processing


class TestDecorator(unittest.TestCase):
    def test_loading_emoji_while_processing_add_and_remove_emoji(self):
        """
            function 동작 이전에 loading 이모지를 추가하고
            function 동작이 마무리되면 loading 이모지를 제거해야만 함.
        """
        mock_f = MagicMock()
        mock_client = MagicMock()
        event = {'client_msg_id': '59d1dbd3-245d-40ec-8898-ec5e32dae2ed', 'type': 'app_mention',
                 'text': '<@U01BN035Y6L>', 'user': 'UQJ8HQJG5', 'ts': '1689437594.220999', 'blocks': [
                {'type': 'rich_text', 'block_id': 'j7p', 'elements': [
                    {'type': 'rich_text_section', 'elements': [{'type': 'user', 'user_id': 'U01BN035Y6L'}]}]}],
                 'team': 'TQLEG4B38', 'thread_ts': '1689437200.559379', 'parent_user_id': 'UQJ8HQJG5',
                 'channel': 'C03SZTDEDK3', 'event_ts': '1689437594.220999'}
        mock_ack = MagicMock()
        mock_say = MagicMock()
        sut = loading_emoji_while_processing()(mock_f)

        sut(client=mock_client, event=event, ack=mock_ack, say=mock_say)

        mock_f.assert_called()
        mock_client.reactions_add.assert_called_once()
        mock_client.reactions_remove.assert_called_once()

    def test_loading_emoji_triggerd_if_target_emoji(self):
        mock_f = MagicMock()
        mock_client = MagicMock()
        event = {'type': 'reaction_added', 'user': 'UQJ8HQJG5', 'reaction': 'thinking',
                 'item': {'type': 'message', 'channel': 'C03SZTDEDK3', 'ts': '1688801145.307229'},
                 'item_user': 'UQJ8HQJG5', 'event_ts': '1688833113.003600'}
        mock_ack = MagicMock()
        mock_say = MagicMock()
        sut = loading_emoji_while_processing(["thinking"])(mock_f)

        sut(client=mock_client, event=event, ack=mock_ack, say=mock_say)

        mock_f.assert_called()
        mock_client.reactions_add.assert_called()
        mock_client.reactions_remove.assert_called()


    def test_loading_emoji_not_triggerd_if_not_target_emoji(self):
        mock_f = MagicMock()
        mock_client = MagicMock()
        event = {'type': 'reaction_added', 'user': 'UQJ8HQJG5', 'reaction': 'thinking',
                 'item': {'type': 'message', 'channel': 'C03SZTDEDK3', 'ts': '1688801145.307229'},
                 'item_user': 'UQJ8HQJG5', 'event_ts': '1688833113.003600'}
        mock_ack = MagicMock()
        mock_say = MagicMock()
        sut = loading_emoji_while_processing(["wink"])(mock_f)

        sut(client=mock_client, event=event, ack=mock_ack, say=mock_say)

        mock_f.assert_called()
        mock_client.reactions_add.assert_not_called()
        mock_client.reactions_remove.assert_not_called()
