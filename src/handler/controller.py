import logging
import traceback

from slack_sdk import WebClient
from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

from config.env_config import envs
from handler.bigchat.abandon_bigchat import AbandonBigchat
from handler.bigchat.announce_new_channel_created import AnnounceNewChannelCreated
from handler.bigchat.create_bigchat_modal import (
    OpenCreateBigchatModal,
    SubmitCreateBigchatModal,
)
from handler.bigchat.create_bigchat_sheet import CreateBigchatSheet
from handler.bigchat.join_bigchat import JoinBigchat
from handler.bigchat.simple_response import SimpleResponse
from handler.bigchat.shuffle_response import ShuffleResponse
from handler.bigchat.mention_response import MentionResponse
from handler.bigchat.remind_bigchat import RemindBigchat
from handler.bigchat.remind_bigchat_command import RemindBigchatCommand
from handler.bigchat.help_response import HelpResponse
from handler.bigchat.question_response import QuestionResponse
from handler.bigchat.subin_like_response import SubinLikeResponse
from handler.decorator import catch_global_error
from handler.loading_emoji import LoadingEmoji
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from implementation.qa_client import QAClient
from implementation.member_finder import MemberManager
from implementation.slack_client import NO_UNFURL, SlackClient
from util.utils import search_value

MEMBER_MANAGER = None
QA_CLIENT = None


def _loading_emoji(slack_client, event) -> LoadingEmoji:
    """이벤트가 가리키는 메시지에 붙일 loading 이모지 컨텍스트.

    이모지를 언제 붙일지는 핸들러가 정한다 — 실제 동작이 없는 이벤트에도 이모지가 붙었다
    떨어지지 않도록, 핸들러가 처리를 시작하는 지점에서만 with 블록으로 감싼다.
    """
    return LoadingEmoji(
        slack_client, search_value(event, "channel"), search_value(event, "ts")
    )


def _get_member_manager():  # TODO(seonghyeok): we need better singleton
    global MEMBER_MANAGER
    if not MEMBER_MANAGER:
        MEMBER_MANAGER = MemberManager(GoogleSpreadsheetClient())
    return MEMBER_MANAGER


def _get_qa_client():
    global QA_CLIENT
    if not QA_CLIENT:
        QA_CLIENT = QAClient(
            qa_server_base_url=envs.QA_SERVER_BASE_URL,
            api_key=envs.QA_API_KEY,
        )
    return QA_CLIENT


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
    slack_client = SlackClient(say, client)
    JoinBigchat(
        event,
        envs.JOIN_BIGCHAT_EMOJI,
        slack_client,
        GoogleSpreadsheetClient(),
        _get_member_manager(),
        loading_emoji=_loading_emoji(slack_client, event),
    ).run()


@catch_global_error()
def abandon_bigchat(event, say, client):
    slack_client = SlackClient(say, client)
    AbandonBigchat(
        event,
        envs.ANNA_ID,
        envs.JOIN_BIGCHAT_EMOJI,
        slack_client,
        _get_member_manager(),
        GoogleSpreadsheetClient(),
        loading_emoji=_loading_emoji(slack_client, event),
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
def mention_response(event, say, client):
    slack_client = SlackClient(say, client)
    help_response = HelpResponse(event, slack_client)
    shuffle_response = ShuffleResponse(event, slack_client)
    simple_response = SimpleResponse(event, slack_client)
    create_bigchat_sheet = CreateBigchatSheet(
        event,
        slack_client,
        GoogleSpreadsheetClient(),
        _get_member_manager(),
        envs.JOIN_BIGCHAT_EMOJI,
    )
    remind_bigchat_command = RemindBigchatCommand(
        event,
        slack_client,
        GoogleSpreadsheetClient(),
        _get_member_manager(),
        envs.ANNA_ID,
    )
    question_response = QuestionResponse(event, slack_client, _get_qa_client())
    # 어느 명령에도 걸리지 않은 멘션은 텍스트 전체를 질문으로 처리 (빈 멘션만 SimpleResponse 로)
    question_fallback = QuestionResponse(
        event, slack_client, _get_qa_client(), require_prefix=False
    )
    # 멘션은 어느 명령에도 걸리지 않아도 폴백(SimpleResponse)이 답하므로 항상 실제 동작이 있다.
    # 따라서 run() 전체를 감싸도 no-op 에 이모지가 붙는 일이 없다.
    with _loading_emoji(slack_client, event):
        MentionResponse(
            [
                question_response,
                shuffle_response,
                # "새로운 빅챗" 보다 먼저 봐야 한다 — 리마인더 명령 문구에도 '빅챗' 이 들어간다
                remind_bigchat_command,
                create_bigchat_sheet,
                help_response,
                question_fallback,
            ],
            simple_response,
        ).run()


# message shortcut(message_action) payload sample (normalize_shortcut_body 적용 후):
# {
#     'type': 'message_action',
#     'callback_id': 'create_bigchat',
#     'trigger_id': '13345224609.738474920.8088930838d88f008e0',
#     'response_url': 'https://hooks.slack.com/app/TQLEG4B38/...',
#     'channel': 'C03SZTDEDK3',   # normalize: {'id': ...} -> id 문자열
#     'ts': '1688801145.307229',  # normalize: 실행한 메시지가 속한 스레드의 첫 글 ts
#     'user': 'UQJ8HQJG5',        # normalize: {'id': ...} -> id 문자열
#     'message': { ... },
#     ...
# }
@catch_global_error()
def open_create_bigchat_modal(event, say, client):
    OpenCreateBigchatModal(event, client).run()


# view_submission payload sample (normalize_view_body 적용 후):
# {
#     'type': 'view_submission',
#     'channel': 'C03SZTDEDK3',   # normalize: private_metadata 에서 복원
#     'ts': '1688801145.307229',  # normalize: private_metadata 에서 복원 (스레드 첫 글 ts)
#     'user': 'UQJ8HQJG5',        # normalize: {'id': ...} -> id 문자열
#     'view': {
#         'callback_id': 'create_bigchat_modal',
#         'private_metadata': '{"channel": ..., "thread_ts": ..., "response_url": ...}',
#         'state': {'values': { ... }},
#         ...
#     },
#     ...
# }
@catch_global_error()
def submit_create_bigchat_modal(event, say, client, ack):
    SubmitCreateBigchatModal(
        event,
        ack,
        SlackClient(say, client),
        GoogleSpreadsheetClient(),
        _get_member_manager(),
        envs.JOIN_BIGCHAT_EMOJI,
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


# 스케줄러(빅챗 전날 저녁)가 부르는 진입점 — 슬랙 이벤트 없이 실행되므로 bolt 의 say/client 가
# 없고, 에러 알림도 catch_global_error 대신 web_client 로 직접 어드민 채널에 보낸다
def remind_bigchat():
    logger = logging.getLogger(__name__)
    logger.info("Bigchat reminder job invoked by scheduler")
    web_client = WebClient(token=envs.SLACK_BOT_TOKEN)
    # 여러 명에게 연속으로 DM 을 보내다 429 를 맞으면 Retry-After 만큼 기다렸다 재시도한다
    web_client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=2))
    try:
        sent_cnt = RemindBigchat(
            SlackClient(None, web_client),
            GoogleSpreadsheetClient(),
            _get_member_manager(),
        ).run()
        logger.info("Bigchat reminder job done: %d DM(s) sent", sent_cnt)
    except Exception:
        logger.exception("Failed to send bigchat reminders")
        try:
            web_client.chat_postMessage(
                channel=envs.ADMIN_CHANNEL,
                text=f":blob-fearful: 빅챗 리마인더 DM 발송 중 에러가 발생했어!\n```\n{traceback.format_exc()}\n```",
                **NO_UNFURL,
            )
        except Exception:
            logger.exception("Failed to notify admin channel")


# message event: 지정 채널(fun-anna-house)의 새 글(스레드 제외)에
# 김수빈 말투로 자동 답글 (대상 채널은 SubinLikeResponse 에 하드코딩)
@catch_global_error()
def subin_like_response(event, say, client):
    SubinLikeResponse(
        event,
        SlackClient(say, client),
        _get_qa_client(),
        anna_id=envs.ANNA_ID,
    ).run()
