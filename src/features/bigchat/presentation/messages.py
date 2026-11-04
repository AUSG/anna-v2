from features.bigchat.errors import (
    BigchatAlreadyCreated,
    BigchatError,
    BigchatIntegrityError,
    BigchatNameConflict,
    BigchatSheetMissing,
)
from shared.utils import strip_multiline


def bigchat_created_message(sheet_url: str, sheet_name: str) -> str:
    # URL은 사용자 안내용이다. 참여 대상은 저장된 스레드 연결로 조회한다.
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
                나를 채널에 초대하면 모집글에서 이모지로 참여 신청을 받을 수 있어!"""
    )


def build_registration_info_message(user: str, member) -> str:
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


def bigchat_storage_error_message(error: BigchatError, action: str) -> str:
    if isinstance(error, BigchatNameConflict):
        return "같은 이름의 빅챗 신청 시트가 이미 있어. 이름과 일정을 확인해서 다시 만들어줘!"
    if isinstance(error, BigchatAlreadyCreated):
        return "이 모집글에는 이미 다른 이름의 빅챗이 연결되어 있어. 기존 신청 시트를 확인해줘!"
    if isinstance(error, BigchatSheetMissing):
        return f"이 빅챗의 신청 시트를 찾을 수 없어서 {action}하지 못했어. 시트가 삭제된 것 같아. 운영진에게 알려줘!"
    if isinstance(error, BigchatIntegrityError):
        return "신청 대상 정보가 일치하지 않아 처리를 중단했어. 신청 시트를 확인하고 운영진에게 알려줘!"
    return f"신청 시트에 접근하거나 {action} 결과를 확인하지 못했어. 잠시 후 다시 시도하고, 계속되면 운영진에게 알려줘!"
