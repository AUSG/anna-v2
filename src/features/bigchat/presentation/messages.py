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
