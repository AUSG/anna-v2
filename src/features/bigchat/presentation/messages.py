from typing import Dict, List

from features.bigchat.models import CancellationStatus, RegistrationStatus
from features.members.models import Member
from shared.text import strip_multiline


def bigchat_created_message(sheet_url: str, sheet_name: str) -> str:
    # 참여 신청은 이 답글의 시트 ID를 기준으로 처리한다.
    return f"새로운 빅챗, 등록 완료! <{sheet_url}|{sheet_name}> :google_spreadsheets:"


def invalid_bigchat_name_message(user: str) -> str:
    return strip_multiline(
        f"""
        <@{user}> 형식이 올바르지 않아서 빅챗을 만들지 않았어. 아래 형식으로 다시 입력해줘!
        `새로운 빅챗 <이름> yy-MM-DD HH:mm~HH:mm`
        예) `새로운 빅챗 AI 밋업 26-08-20 19:00~21:00`
        (실제 존재하는 날짜/시각이어야 하고, 종료 시각은 시작보다 늦어야 해!)"""
    )


def bot_not_in_channel_message(sheet_url: str, sheet_name: str) -> str:
    return strip_multiline(
        f"""
                시트(<{sheet_url}|{sheet_name}>)는 만들었는데, 내가 이 채널에 없어서 스레드에 답글을 못 달았어.
                나를 채널에 초대한 뒤 위 시트 링크를 스레드에 공유해줘. 그래야 이모지로 참여 신청을 받을 수 있어!"""
    )


def build_registration_info_message(user: str, member: Member) -> str:
    return strip_multiline(
        f"""
        <@{user}> 네 신청 정보를 아래와 같이 등록했어. 바뀐 부분이 있다면 운영진에게 DM으로 알려줘!
        ```
        이름(영문): {member.kor_name}({member.eng_name})
        핸드폰: {member.phone}
        이메일: {member.email}
        학교/회사: {member.school_name_or_company_name}
        ```
        (참고로 이 메시지는 너만 볼 수 있어!)"""
    )


def registered_message(user: str) -> str:
    return f"<@{user}>, 등록 완료!"


REGISTRATION_NOTICES: Dict[RegistrationStatus, str] = {
    RegistrationStatus.ALREADY_REGISTERED: "<@{user}>, 이미 등록되어 있어!",
    RegistrationStatus.MEMBER_NOT_FOUND: "<@{user}>, 네 정보를 찾지 못했어. 운영진에게 연락해줘!",
    RegistrationStatus.MEMBER_LACKS_INFO: "<@{user}>, 네 정보에 누락된 값이 있어. 운영진에게 연락해줘!",
    RegistrationStatus.WORKSHEET_MISSING: (
        "<@{user}>, 이 빅챗의 신청 시트를 찾을 수 없어. 이미 마감되었거나 삭제된 것 같아. "
        "모집이 진행 중인 빅챗이라면 운영진에게 알려줘!"
    ),
}


def registration_notice(status: RegistrationStatus, user: str) -> str:
    return REGISTRATION_NOTICES[status].format(user=user)


def cancelled_message(user: str) -> str:
    return f"<@{user}>, 등록을 취소했어."


CANCELLATION_NOTICES: Dict[CancellationStatus, str] = {
    CancellationStatus.MEMBER_NOT_FOUND: "<@{user}>, 네 정보를 찾지 못했어.",
    CancellationStatus.MEMBER_LACKS_INFO: "<@{user}>, 네 정보에 누락된 값이 있어.",
    CancellationStatus.WORKSHEET_MISSING: (
        "<@{user}>, 이 빅챗의 신청 시트를 찾을 수 없어서 등록을 취소하지 못했어. "
        "이미 마감되었거나 삭제된 것 같아. 필요하면 운영진에게 알려줘!"
    ),
}


def cancellation_notice(status: CancellationStatus, user: str) -> str:
    return CANCELLATION_NOTICES[status].format(user=user)


def early_reactions_registered_message(users: List[str], target_emoji: str) -> str:
    mentions = " ".join(f"<@{user}>" for user in users)
    return f"{mentions} 시트가 만들어지기 전에 :{target_emoji}:를 눌러줬구나! 지금 등록 완료했어!"


def early_reactions_failed_message(target_emoji: str) -> str:
    return (
        f"미리 눌린 :{target_emoji}: 자동 등록을 처리하다 문제가 생겨서 멈췄어. "
        "등록되지 않은 사람이 있을 수 있으니 시트를 확인해줘!"
    )
