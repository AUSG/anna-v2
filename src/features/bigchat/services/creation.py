import logging

from slack_sdk.errors import SlackApiError

from features.bigchat.presentation.messages import build_registration_info_message
from features.members.services.directory import MemberLackInfo, MemberNotFound

logger = logging.getLogger(__name__)


def register_early_reacted_users(
    slack_client,
    gs_client,
    member_manager,
    target_emoji,
    worksheet_id,
    channel,
    thread_ts,
):
    """시트 게시 뒤 미리 달린 참여 반응을 등록한다. (#89)

    등록 중 오류는 재생성 대신 스레드 경고를 시도한다.
    """
    reaction = slack_client.get_emoji(
        channel=channel, ts=thread_ts, emoji_name=target_emoji
    )
    if reaction is None:
        return

    try:
        registered = []
        for user in reaction.users:
            try:
                member = member_manager.find(user)
            except MemberNotFound:
                slack_client.send_thread_message(
                    msg=f"<@{user}>, 네 정보를 찾지 못했어. 운영진에게 연락해줘!",
                    channel=channel,
                    ts=thread_ts,
                )
            except MemberLackInfo:
                slack_client.send_thread_message(
                    msg=f"<@{user}>, 네 정보에 누락된 값이 있어. 운영진에게 연락해줘!",
                    channel=channel,
                    ts=thread_ts,
                )
            else:
                if gs_client.append_row_if_absent(
                    worksheet_id, member.transform_for_spreadsheet()
                ):
                    registered.append((user, member))

        if not registered:
            return

        mentions = " ".join(f"<@{user}>" for user, _ in registered)
        slack_client.send_thread_message(
            msg=f"{mentions} 시트가 만들어지기 전에 :{target_emoji}:를 눌러줬구나! 지금 등록 완료했어!",
            channel=channel,
            ts=thread_ts,
        )
        for user, member in registered:
            try:
                slack_client.send_message_only_visible_to_user(
                    msg=build_registration_info_message(user, member),
                    channel=channel,
                    ts=thread_ts,
                    user_id=user,
                )
            except SlackApiError as ex:
                # 슬랙 API 오류로 안내하지 못해도 다음 사용자로 진행한다.
                logger.warning("Failed to send registration info to %s: %s", user, ex)
    except Exception:
        logger.exception("Failed to backfill early reactions")
        slack_client.send_thread_message(
            msg=f"미리 눌린 :{target_emoji}: 자동 등록을 처리하다 문제가 생겨서 멈췄어. "
            "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!",
            channel=channel,
            ts=thread_ts,
        )
