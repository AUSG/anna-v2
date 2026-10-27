"""등록 안내의 Slack 블록 표현. URL과 이벤트 조회는 호출자가 담당한다."""

from typing import Optional


def registration_blocks(
    msg: str, gcal_url: str, ics_url: Optional[str] = None
) -> list[dict]:
    buttons = [
        {
            "type": "button",
            "action_id": "calendar_gcal",
            "text": {
                "type": "plain_text",
                "text": "📅 Google Calendar에 추가",
                "emoji": True,
            },
            "url": gcal_url,
        }
    ]
    if ics_url:
        buttons.append(
            {
                "type": "button",
                "action_id": "calendar_ics",
                "text": {"type": "plain_text", "text": "📥 .ics 다운로드", "emoji": True},
                "url": ics_url,
            }
        )
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": msg}},
        {"type": "actions", "elements": buttons},
    ]
