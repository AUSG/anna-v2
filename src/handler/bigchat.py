from config.env_config import envs
from handler.bigchat.abandon_bigchat import AbandonBigchat
from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from handler.bigchat.join_bigchat import JoinBigchat
from handler.bigchat.simple_response import SimpleResponse
from handler.decorator import catch_global_error, loading_emoji_while_processing
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from implementation.member_finder import MemberManager
from implementation.slack_client import SlackClient

MEMBER_MANAGER = None


def _get_member_manager():  # TODO(seonghyeok): we need better singleton
    global MEMBER_MANAGER
    if not MEMBER_MANAGER:
        MEMBER_MANAGER = MemberManager(GoogleSpreadsheetClient())
    return MEMBER_MANAGER


# reaction_added event sample:
# {
#   'type': 'reaction_added',
#   'user': 'UQJ8HQJG5',
#   'reaction': 'kirbyok',
#   'item': {
#     'type': 'message',
#     'channel': 'C03SZTDEDK3',
#     'ts': '1688801145.307229'
#   },
#   'item_user': 'UQJ8HQJG5',
#   'event_ts': '1688833113.003600'
# }
@catch_global_error()
def join_bigchat(event, say, client):
    JoinBigchat(
        event,
        envs.JOIN_BIGCHAT_EMOJI,
        SlackClient(say, client),
        GoogleSpreadsheetClient(),
        _get_member_manager(),
    ).run()


@catch_global_error()
@loading_emoji_while_processing()
def abandon_bigchat(event, say, client):
    AbandonBigchat(
        event,
        envs.ANNA_ID,
        envs.JOIN_BIGCHAT_EMOJI,
        SlackClient(say, client),
        _get_member_manager(),
        GoogleSpreadsheetClient(),
    ).run()


# app_mention event sample:
# {
#     'client_msg_id': '8fb50d48-f93d-4cca-b9ca-6965479e9a93',
#     'type': 'app_mention',
#     'text': msg,
#     'user': 'UQJ8HQJG5',
#     'ts': '1689403771.805849',
#     'blocks': [ ... ],  # not used and too long, so skipped
#     'team': 'TQLEG4B38',
#     'thread_ts': '1689403100.222939',
#     'parent_user_id': 'UQJ8HQJG5',
#     'channel': 'C03SZTDEDK3',
#     'event_ts': '1689403771.805849'
# }
@catch_global_error()
@loading_emoji_while_processing()
def create_bigchat_sheet(event, say, client):
    CreateBigchatSheet(event, SlackClient(say, client), GoogleSpreadsheetClient()).run()


@catch_global_error()
@loading_emoji_while_processing()
def simple_response(event, say, client):
    SimpleResponse(event, SlackClient(say, client)).run()
