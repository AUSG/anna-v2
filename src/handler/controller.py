from config.env_config import envs
from handler.bigchat.abandon_bigchat import AbandonBigchat
from handler.bigchat.announce_new_channel_created import AnnounceNewChannelCreated
from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from handler.bigchat.join_bigchat import JoinBigchat
from handler.bigchat.simple_response import SimpleResponse
from handler.bigchat.shuffle_response import ShuffleResponse
from handler.bigchat.mention_response import MentionResponse
from handler.bigchat.help_response import HelpResponse
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
@loading_emoji_while_processing([envs.JOIN_BIGCHAT_EMOJI])
def join_bigchat(event, say, client):
    JoinBigchat(
        event,
        envs.JOIN_BIGCHAT_EMOJI,
        SlackClient(say, client),
        GoogleSpreadsheetClient(),
        _get_member_manager(),
    ).run()


@catch_global_error()
@loading_emoji_while_processing([envs.JOIN_BIGCHAT_EMOJI])
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
def mention_response(event, say, client):
    help_response = HelpResponse(event, SlackClient(say, client))
    shuffle_response = ShuffleResponse(event, SlackClient(say, client))
    simple_response = SimpleResponse(event, SlackClient(say, client))
    create_bigchat_sheet = CreateBigchatSheet(
        event, SlackClient(say, client), GoogleSpreadsheetClient()
    )
    MentionResponse(
        [shuffle_response, create_bigchat_sheet, help_response], simple_response
    ).run()


# channel_created event sample:
# {
#     'type': 'channel_created',
#     'channel': {
#         'id': 'C07DB6LPCJE',
#         'name': 'test-create-channel-2',
#         'is_channel': True,
#         'is_group': False,
#         'is_im': False,
#         'is_mpim': False,
#         'is_private': False,
#         'created': 1721484974,
#         'is_archived': False,
#         'is_general': False,
#         'unlinked': 0,
#         'name_normalized': 'test-create-channel-2',
#         'is_shared': False,
#         'is_frozen': False,
#         'is_org_shared': False,
#         'is_pending_ext_shared': False,
#         'pending_shared': [],
#         'context_team_id': 'TQLEG4B38',
#         'updated': 1721484974161,
#         'parent_conversation': None,
#         'creator': 'UQJ8HQJG5',
#         'is_ext_shared': False,
#         'shared_team_ids': [
#             'TQLEG4B38'
#         ],
#         'pending_connected_team_ids': [],
#         'topic': {
#             'value': '',
#             'creator': '',
#             'last_set': 0
#         },
#         'purpose': {
#             'value': '',
#             'creator': '',
#             'last_set': 0
#         },
#         'previous_names': []
#     },
#     'event_ts': '1721484974.006000'
# }
@catch_global_error()
def announce_new_channel_created(event, say, client):
    AnnounceNewChannelCreated(event, SlackClient(say, client)).run()
