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

# 302 리다이렉트로 내려주는 gcal URL의 안전 상한 (브라우저/구글 프론트엔드의 ~8k 제한 대비 여유)
GCAL_URL_LIMIT = 6000


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


def to_gcal_link(event: BigchatEvent, details: str = "") -> str:
    params = {
        "action": "TEMPLATE",
        "text": event.name,
        "dates": f"{_fmt_local(event.start)}/{_fmt_local(event.end)}",
        "ctz": "Asia/Seoul",
    }
    if details:
        params["details"] = details
    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"


def to_gcal_link_truncated(
    event: BigchatEvent, details: str = "", limit: int = GCAL_URL_LIMIT
) -> str:
    """URL 길이 제한에 맞을 때까지 details를 잘라낸 gcal 링크."""
    link = to_gcal_link(event, details)
    while len(link) > limit and details:
        details = details[: len(details) - 100]
        link = to_gcal_link(event, details + "…" if details else "")
    return link


def to_ics(event: BigchatEvent, uid: str, description: str = "") -> str:
    # KST는 DST가 없으므로 UTC로 변환해 VTIMEZONE 블록을 생략한다
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AUSG//anna//KO",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt_utc(datetime.now(tz=timezone.utc))}",
        f"DTSTART:{_fmt_utc(event.start)}",
        f"DTEND:{_fmt_utc(event.end)}",
        f"SUMMARY:{_escape_ics_text(event.name)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape_ics_text(description)}")
    lines += [
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join([_fold_ics_line(line) for line in lines] + [""])


def calendar_payload(worksheet_id: int, channel: str, ts: str) -> str:
    return f"{worksheet_id}:{channel}:{ts}"


def calendar_token(secret: str, payload: str) -> str:
    """gcal 리다이렉트와 ics 다운로드가 같은 토큰을 공유한다 (시크릿 env는 ICS_TOKEN_SECRET 그대로)."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_calendar_token(secret: str, payload: str, token: str) -> bool:
    return hmac.compare_digest(calendar_token(secret, payload), token)


def _fmt_local(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%S")


def _fmt_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape_ics_text(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold_ics_line(line: str) -> str:
    """RFC 5545 3.1: 75 옥텟을 넘는 줄은 CRLF + 공백으로 접는다 (멀티바이트 문자는 중간에서 자르지 않음)."""
    if len(line.encode("utf-8")) <= 75:
        return line

    parts, current = [], ""
    for char in line:
        limit = 75 if not parts else 74  # 이어지는 줄은 맨 앞 공백 1칸 몫을 뺀다
        if len((current + char).encode("utf-8")) > limit:
            parts.append(current)
            current = char
        else:
            current += char
    parts.append(current)
    return "\r\n ".join(parts)
