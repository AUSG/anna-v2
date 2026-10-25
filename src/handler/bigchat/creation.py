import logging

from slack_sdk.errors import SlackApiError

from application.bigchat import BigchatCreated
from handler.bigchat.messages import build_registration_info_message
from implementation.google_spreadsheet_client import GoogleSpreadsheetClient
from implementation.member_finder import MemberLackInfo, MemberNotFound

logger = logging.getLogger(__name__)


class SpreadsheetBigchatRepository:
    def __init__(self, client: GoogleSpreadsheetClient):
        self._client = client

    def create(self, sheet_name: str) -> BigchatCreated:
        worksheet_id = self._client.create_bigchat_sheet(sheet_name)
        return BigchatCreated(
            worksheet_id=worksheet_id,
            sheet_name=sheet_name,
            sheet_url=self._client.get_url(worksheet_id),
        )


def register_early_reacted_users(
    slack_client,
    gs_client,
    member_manager,
    target_emoji,
    worksheet_id,
    channel,
    thread_ts,
):
    """시트가 생기기 전에 모집글에 :gogo:를 누른 사람들을 일괄 등록한다. (#89)

    멘션·모달 두 경로 모두 시트 링크 답글을 올린 직후에 호출해야 한다.
    링크 게시 이후의 반응은 JoinBigchat이 처리하며, 거의 동시에 같은 사람을
    처리해도 append_row_if_absent가 중복 등록을 막는다.

    시트 생성과 링크 안내는 이미 성공했으므로, 일괄 등록 실패는 스레드에 경고만
    남긴다. 전체 요청을 실패 처리하면 사용자가 같은 시트를 다시 만들 수 있다.
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
                # 채널을 떠났거나 비활성화된 반응자에게는 ephemeral을 못 보낸다.
                # 등록 자체는 이미 끝났으므로 나머지 인원 안내를 계속한다.
                logger.warning(f"Failed to send registration info to {user}: {ex}")
    except Exception:
        logger.exception("Failed to backfill early reactions")
        slack_client.send_thread_message(
            msg=f"미리 눌린 :{target_emoji}: 자동 등록을 처리하다 문제가 생겨서 멈췄어. "
            "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!",
            channel=channel,
            ts=thread_ts,
        )
