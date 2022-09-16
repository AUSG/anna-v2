import os
import re
from typing import Union, Tuple, List

from slack_bolt import Say
from slack_sdk import WebClient

from exception import RuntimeException
from implementation import google_spreadsheet_client, GoogleSpreadsheetClient
from util import get_prop, SlackGeneralEvent
from .member import Member
from .member_finder import find_member, validate_member_info

ANNOUNCEMENT_CHANNEL_ID = os.environ.get('ANNOUNCEMENT_CHANNEL_ID')
ANNA_ID = os.environ.get('ANNA_ID')
ORGANIZER_ID = os.environ.get('ORGANIZER_ID')
SUBMIT_FORM_EMOJI = os.environ.get('SUBMIT_FORM_EMOJI')
SUSPEND_FORM_EMOJI = os.environ.get('SUSPEND_FORM_EMOJI')
MEMBERS_INFO_WORKSHEET_ID = int(os.environ.get('MEMBERS_INFO_WORKSHEET_ID'))
FORM_SPREADSHEET_ID = os.environ.get('FORM_SPREADSHEET_ID')


class EmojiAddedEvent:
    """
    data class
    """

    def __init__(self, ts: str, channel: str, slack_unique_id: str):
        self.ts = ts
        self.channel = channel
        self.slack_unique_id = slack_unique_id


def participate_offline_meeting(event: SlackGeneralEvent, say: Say, web_client: WebClient):
    if not is_target_emoji(event, web_client):
        return

    if organizer_put_suspend_emoji(event, web_client):
        say(text=f"오거나이저가 :stop2: 이모지를 붙여놨기 때문에 <@{get_prop(event, 'user')}>의 요청을 들어줄 수가 없어.", thread_ts=get_prop(event, 'item', 'ts'))
        return

    gs_client = google_spreadsheet_client.get_instance()
    event = EmojiAddedEvent(event['item']['ts'], event['item']['channel'], event['user'])
    member = find_member(gs_client, event.slack_unique_id)
    if member is None:
        raise RuntimeException(f"멤버 정보를 찾지 못했어요. (slack_unique_id: {event.slack_unique_id})", thread_ts=event.ts)
    elif not validate_member_info(member):
        raise RuntimeException(f"멤버 정보가 완벽하지 않아요. (slack_unique_id: {event.slack_unique_id}, member_info: {member})",
                               thread_ts=event.ts)

    is_new, worksheet_id = get_worksheet_id(web_client, gs_client, event.ts, event.channel)
    if is_new:
        url = gs_client.get_url(FORM_SPREADSHEET_ID, worksheet_id)
        say(text=f"새로운 시트를 만들었어! <{url}|구글스프레드 시트>", thread_ts=event.ts)

    submit_form(gs_client, FORM_SPREADSHEET_ID, worksheet_id, member)
    say(text=f"<@{event.slack_unique_id}>, 등록 완료!", thread_ts=event.ts)


def is_target_emoji(event: SlackGeneralEvent, web_client: WebClient) -> bool:
    if get_prop(event, 'type') != 'reaction_added':
        return False
    elif get_prop(event, 'reaction') != SUBMIT_FORM_EMOJI:
        return False
    elif get_prop(event, 'subtype') is not None:
        return False
    elif get_prop(event, 'user') is None:
        return False
    elif get_prop(event, 'item', 'ts') is None:
        return False
    elif get_prop(event, 'item', 'channel') != ANNOUNCEMENT_CHANNEL_ID:
        return False
    elif is_reply_in_thread(web_client, get_prop(event, 'item', 'ts'), get_prop(event, 'item', 'channel')):
        return False
    return True


def organizer_put_suspend_emoji(event: SlackGeneralEvent, web_client: WebClient) -> bool:
    emoji_with_users_list = get_emojis_on_message(event, web_client)

    for emoji_with_users in emoji_with_users_list:
        if emoji_with_users['name'] == SUSPEND_FORM_EMOJI and ORGANIZER_ID in emoji_with_users['users']:
            return True

    return False


def get_emojis_on_message(event, web_client):
    resp = web_client.reactions_get(
        channel=get_prop(event, 'item', 'channel'),
        timestamp=get_prop(event, 'item', 'ts'),
        full=True
    )
    emoji_with_users_list: List[object] = get_prop(resp, 'message', 'reactions')
    return emoji_with_users_list


def is_reply_in_thread(web_client: WebClient, ts: str, channel: str):
    # [FIXME] default 값이 해당 쓰레드의 메시지 1000 개를 가져오는 것인데,
    #     혹시라도 쓰레드의 댓글이 첫 글 포함 1000개가 넘을경우 먼저 작성된 1000개를 가져올지, 나중에 작성된 1000개를 가져올지에 대해 체크해보지 않음.
    #     만약 후자일 경우 이 코드가 쓰레드의 제일 첫번째 메시지를 가져올 수 있도록 수정해야 함
    resp = web_client.conversations_replies(ts=ts, channel=channel)
    first_message = resp['messages'][0]

    if 'thread_ts' not in first_message:  # 아직 댓글이 하나도 없음
        return False
    elif first_message['thread_ts'] == first_message['ts']:  # 해당 쓰레드의 첫 번째 글임
        return False
    else:
        return True


def get_worksheet_id(web_client: WebClient, gs_client: GoogleSpreadsheetClient, ts: str, channel: str) \
        -> Tuple[bool, int]:
    """
    :return: (is_new, worksheet_id)
    """
    worksheet_id = find_worksheet_id_in_thread(web_client, ts, channel)

    if worksheet_id is not None:
        is_new = False
    else:
        is_new = True
        worksheet_id = gs_client.create_worksheet(
            spreadsheet_id=FORM_SPREADSHEET_ID,
            title_prefix="[제목바꿔줘]",
            header_values=["타임스탬프", "이메일 주소", "이름", "영문 이름", "휴대폰 번호", "학교명 혹은 회사명"]
        )

    return is_new, worksheet_id


def find_worksheet_id_in_thread(web_client: WebClient, ts: str, channel: str) -> Union[int, None]:
    response = web_client.conversations_replies(ts=ts, channel=channel)
    spreadsheet_url_pattern = r'https:\/\/docs.google.com\/spreadsheets\/d\/.*\/edit#gid=(\d*)'

    for message in response['messages']:
        if message['user'] == ANNA_ID:
            pat = re.search(spreadsheet_url_pattern, message['text'])
            if pat is not None and len(pat.groups()) > 0:
                return int(pat.groups()[0])
    return None


def submit_form(gs_client: GoogleSpreadsheetClient, spreadsheet_id: str, worksheet_id: int, member: Member):
    gs_client.append_row(spreadsheet_id=spreadsheet_id,
                         worksheet_id=worksheet_id,
                         values=member_to_list(member))


def member_to_list(member):
    return [member.email,
            member.kor_name,
            member.eng_name,
            member.phone,
            member.school_name_or_company_name]
