from config.env_config import envs
from handler.decorator import catch_global_error
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from implementation.member_finder import MemberFinder
from implementation.slack_client import SlackClient

FORM_SPREADSHEET_ID = envs.FORM_SPREADSHEET_ID

gs_client = GoogleSpreadsheetClient()
member_finder = MemberFinder()


# event sample:
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
@catch_global_error
def attend_bigchat(event, say, client):
    slack_client = SlackClient(say, client)

    event_type = event["type"]
    event_reaction = event["reaction"]
    event_channel = event["item"]["channel"]
    event_ts = event["item"]["ts"]
    event_user = event["user"]

    if (
        event_type != "reaction_added"
        or event_reaction != envs.JOIN_BIGCHAT_EMOJI
        or event_channel != envs.ANNOUNCEMENT_CHANNEL_ID
        or event_ts != slack_client.get_replies(event_ts, event_channel)[0].ts
    ):
        return

    member = member_finder.find(event_user)

    worksheet_id = gs_client.find_or_create_worksheet(
        slack_client,
        event_ts,
        event_channel,
        FORM_SPREADSHEET_ID,
        callback_for_new_worksheet=lambda new_worksheet_id: slack_client.send_message(
            msg=f"새로운 시트를 만들었어! <{gs_client.get_url(FORM_SPREADSHEET_ID, new_worksheet_id)}|구글스프레드 시트>",
            ts=event_ts,
        ),
    )

    gs_client.append_row(FORM_SPREADSHEET_ID, worksheet_id, member.to_list())

    slack_client.send_message(msg=f"<@{event_user}>, 등록 완료!", ts=event_ts)

    slack_client.send_message_only_visible_to_user(
        msg=f"""
<@{event_user}> 네 신청 정보를 아래와 같이 입력했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
```
핸드폰: {member.phone}
이메일: {member.email}
학교/회사: {member.school_name_or_company_name}
```
(참고로 이 메시지는 너만 볼 수 있어!)""",
        channel=event_channel,
        thread_ts=event_ts,
        user=event_user,
    )


@catch_global_error
def abandon_bigchat(_event, _say, _client):
    pass
