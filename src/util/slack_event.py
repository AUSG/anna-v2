"""슬랙 이벤트 판별 헬퍼."""


def is_edited_message(event) -> bool:
    """이미 올라온 메시지를 고쳐서 온 이벤트인지.

    슬랙은 메시지 '수정'에도 이벤트를 보내는데, 새 글과 똑같이 처리하면
    같은 멘션 명령이 한 번 더 실행되고(리마인더 재발송 등) 답글도 중복으로 달린다.
    수정 사실은 이벤트 종류마다 다른 자리에 실려온다:

    - message: subtype 이 'message_changed' 이고, 본문은 event['message'] 아래로 내려간다
    - app_mention: 최상위에 'edited' 가 붙는다 (이미 있던 멘션을 고치면 다시 발생)
    """
    if not isinstance(event, dict):
        return False
    if event.get("subtype") == "message_changed":
        return True
    if event.get("edited"):
        return True
    if (event.get("message") or {}).get("edited"):
        return True
    return False
