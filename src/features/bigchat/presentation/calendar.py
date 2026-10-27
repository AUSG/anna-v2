"""빅챗 이벤트를 캘린더 URL 또는 ICS로 표현한다. 외부 조회는 하지 않는다."""

from datetime import datetime, timezone
from urllib.parse import urlencode

from features.bigchat.models import BigchatEvent


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
    event: BigchatEvent, details: str = "", limit: int = 2900
) -> str:
    """전달받은 URL 길이 제한에 맞춰 설명을 뒤에서 줄인다."""
    link = to_gcal_link(event, details)
    while len(link) > limit and details:
        details = details[: len(details) - 100]
        link = to_gcal_link(event, details + "…" if details else "")
    return link


def to_ics(event: BigchatEvent, uid: str, description: str = "") -> str:
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
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join([_fold_ics_line(line) for line in lines] + [""])


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
    """RFC 5545: UTF-8 문자 경계를 보존해 75 옥텟 이내로 접는다."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts, current = [], ""
    for char in line:
        limit = 75 if not parts else 74
        if len((current + char).encode("utf-8")) > limit:
            parts.append(current)
            current = char
        else:
            current += char
    parts.append(current)
    return "\r\n ".join(parts)
