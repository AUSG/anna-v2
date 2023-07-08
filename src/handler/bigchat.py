from config.env_config import envs
from config.log_config import get_logger
from handler.decorator import catch_global_error
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from implementation.member_finder import MemberManager
from implementation.slack_client import SlackClient

FORM_SPREADSHEET_ID = envs.FORM_SPREADSHEET_ID

member_manager = MemberManager(GoogleSpreadsheetClient())


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
    # set variables
    slack_client = SlackClient(say, client)
    event_type = event["type"]
    event_reaction = event["reaction"]
    event_channel = event["item"]["channel"]
    event_ts = event["item"]["ts"]
    event_user = event["user"]

    # check if the event is for me
    if (
        event_type != "reaction_added"
        or event_reaction != envs.JOIN_BIGCHAT_EMOJI
        # or event_channel != envs.ANNOUNCEMENT_CHANNEL_ID
        or event_ts != slack_client.get_replies(event_ts, event_channel)[0].ts
    ):
        return

    # get member info
    member = member_manager.find(event_user)

    # add member info to spreadsheet
    is_added = member_manager.add_member_to_bigchat_worksheet(
        member, slack_client, event_ts, event_channel, envs.FORM_SPREADSHEET_ID
    )

    if not is_added:
        slack_client.send_message_only_visible_to_user(
            f"(<@{event_user}>, 넌 이미 등록되어 있어)", event_user, event_channel, event_ts
        )
        return

    # send result to user
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
def abandon_bigchat(event, say, client):
    # set variables
    slack_client = SlackClient(say, client)
    event_type = event["type"]
    event_reaction = event["reaction"]
    event_channel = event["item"]["channel"]
    event_ts = event["item"]["ts"]
    event_user = event["user"]

    get_logger().info("event: %s", event)

    # check if the event is for me
    if (
        event_type != "reaction_removed"
        or event_reaction != envs.JOIN_BIGCHAT_EMOJI
        # or event_channel != envs.ANNOUNCEMENT_CHANNEL_ID
        or event_ts != slack_client.get_replies(event_ts, event_channel)[0].ts
    ):
        return

    is_removed = member_manager.remove_member_from_bigchat_worksheet(
        event_user, slack_client, event_ts, event_channel, FORM_SPREADSHEET_ID
    )
    if not is_removed:
        slack_client.send_message_only_visible_to_user(
            f"""<@{event_user}>, 네 이름을 지울 수가 없었어. 정상적으로 등록이 안 된 것 않은데... 
만약 등록을 취소해야 한다면 운영진에게 연락해줘!""",
            event_user,
            event_channel,
            event_ts,
        )
        return

    slack_client.send_message(
        f"<@{event_user}>, 등록을 취소했어,, 다시 등록하려면 운영진에게 따로 연락해줘!", event_ts
    )
