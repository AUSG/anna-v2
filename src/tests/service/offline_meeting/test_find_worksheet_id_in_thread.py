from tests.util import enable_dummy_envs

enable_dummy_envs()

#
# def test_none_with_empty_response():
#     with patch('slack_sdk.web.WebClient') as mock_web_client:
#         mock_web_client.mock_conversations_replies.return_value = {'messages': [{'user': "asd", 'text': 'hello'}]}
#
#         assert _find_worksheet_id_in_thread(mock_web_client, None, None) is None
#
#
# def test_none_when_spreadsheet_url_pattern_not_in_messages():
#     with patch('slack_sdk.web.WebClient') as mock_web_client:
#         mock_web_client.mock_conversations_replies.return_value = {'messages': [{'user': "me", 'text': 'hello'}]}
#
#         assert _find_worksheet_id_in_thread(mock_web_client, None, None) is None
#
#
# def test_none_when_spreadsheet_url_pattern_in_messages_not_by_anna():
#     with patch('slack_sdk.web.WebClient') as mock_web_client:
#         mock_web_client.mock_conversations_replies.return_value = {'messages': [{'user': "me", 'text': 'https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=1234'}]}
#
#         assert _find_worksheet_id_in_thread(mock_web_client, None, None) is None
#
#
# def test_none_when_spreadsheet_url_pattern_not_in_messages_by_anna():
#     with patch('slack_sdk.web.WebClient') as mock_web_client:
#         mock_web_client.conversations_replies.return_value = {'messages': [{'user': os.environ.get('ANNA_ID'), 'text': 'https://docs.google.com'}]}
#
#         assert _find_worksheet_id_in_thread(mock_web_client, None, None) is None
#
#
# def test_success_when_spreadsheet_url_pattern_in_messages_by_anna():
#     with patch('slack_sdk.web.WebClient') as mock_web_client:
#         mock_web_client.conversations_replies.return_value = {'messages': [{'user': os.environ.get('ANNA_ID'), 'text': 'https://docs.google.com/spreadsheets/d/1FtKRO4gmlVg-Si0_CHt-tkpVd3LDTXdsoZ0u98MYd0k/edit#gid=1234'}]}
#
#         assert _find_worksheet_id_in_thread(mock_web_client, None, None) == 1234
