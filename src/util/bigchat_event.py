import hashlib
import hmac
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from dateutil.tz import gettz

KST = gettz("Asia/Seoul")

# 빅챗 시트 이름이 곧 이벤트 정보 저장소다: "<name> yy-MM-DD HH:mm~HH:mm"
# e.g. "AI 밋업 26-08-20 19:00~21:00"
SHEET_NAME_PAT = re.compile(
    r"^(?P<name>.+) (?P<date>\d{2}-\d{2}-\d{2}) (?P<start>\d{2}:\d{2})~(?P<end>\d{2}:\d{2})$"
)


@dataclass
class BigchatEvent:
    name: str
    start: datetime  # tz-aware (KST)
    end: datetime  # tz-aware (KST)


def parse_sheet_name(sheet_name: str) -> Optional[BigchatEvent]:
    """포맷 불일치, 존재하지 않는 날짜/시각, 종료가 시작보다 빠르거나 같으면 None (보정 없음)."""
    match = SHEET_NAME_PAT.match(sheet_name.strip())
    if not match:
        return None

    try:
        start = datetime.strptime(
            f"{match['date']} {match['start']}", "%y-%m-%d %H:%M"
        ).replace(tzinfo=KST)
        end = datetime.strptime(
            f"{match['date']} {match['end']}", "%y-%m-%d %H:%M"
        ).replace(tzinfo=KST)
    except ValueError:
        return None

    if end <= start:
        return None

    return BigchatEvent(name=match["name"].strip(), start=start, end=end)


def to_gcal_link(event: BigchatEvent) -> str:
    params = urlencode(
        {
            "action": "TEMPLATE",
            "text": event.name,
            "dates": f"{_fmt_local(event.start)}/{_fmt_local(event.end)}",
            "ctz": "Asia/Seoul",
        }
    )
    return f"https://calendar.google.com/calendar/render?{params}"


def to_ics(event: BigchatEvent, uid: str) -> str:
    # KST는 DST가 없으므로 UTC로 변환해 VTIMEZONE 블록을 생략한다
    return "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//AUSG//anna//KO",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_fmt_utc(datetime.now(tz=timezone.utc))}",
            f"DTSTART:{_fmt_utc(event.start)}",
            f"DTEND:{_fmt_utc(event.end)}",
            f"SUMMARY:{_escape_ics_text(event.name)}",
            "END:VEVENT",
            "END:VCALENDAR",
            "",
        ]
    )


def ics_token(secret: str, worksheet_id: int) -> str:
    return hmac.new(
        secret.encode(), str(worksheet_id).encode(), hashlib.sha256
    ).hexdigest()


def verify_ics_token(secret: str, worksheet_id: int, token: str) -> bool:
    return hmac.compare_digest(ics_token(secret, worksheet_id), token)


def _fmt_local(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape_ics_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )
