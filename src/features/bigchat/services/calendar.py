"""캘린더 링크 발급, 다운로드 접근 검증과 필요한 데이터 조회."""

import hashlib
import hmac
import logging
from urllib.parse import urlencode

from features.bigchat.models import (
    CalendarAccessDenied,
    CalendarUnavailable,
    parse_sheet_name,
)
from features.bigchat.presentation.blocks import (
    SLACK_BUTTON_URL_LIMIT,
    registration_blocks,
)
from features.bigchat.presentation.calendar import to_gcal_link_truncated

logger = logging.getLogger(__name__)


def calendar_payload(worksheet_id: int, channel: str, ts: str) -> str:
    return f"{worksheet_id}:{channel}:{ts}"


def calendar_token(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_calendar_token(secret: str, payload: str, token: str) -> bool:
    return hmac.compare_digest(calendar_token(secret, payload), token)


def build_registration_calendar_blocks(
    msg,
    worksheet_id,
    intro_text,
    channel,
    ts,
    slack_client,
    gs_client,
    *,
    public_base_url,
    token_secret,
):
    """등록 성공 뒤 제공할 캘린더 안내. 부가 조회 실패는 등록을 실패시키지 않는다.

    Google Calendar는 모바일 앱 핸드오프를 위해 리다이렉트 없는 직링크로 제공한다.
    설명의 맨 앞에 permalink를 두어 URL 길이를 줄여도 원문 링크는 유지한다.
    ICS는 클릭 시점에 소개글 전문을 조회한다.
    """
    try:
        event = parse_sheet_name(gs_client.get_worksheet_title(worksheet_id))
    except Exception as ex:
        logger.warning(f"Failed to build calendar buttons: {ex}")
        return None
    if not event:
        return None
    permalink = slack_client.get_permalink(channel, ts)
    details = f"슬랙에서 소개글 보기: {permalink}\n\n{intro_text}" if permalink else intro_text
    gcal_url = to_gcal_link_truncated(event, details, limit=SLACK_BUTTON_URL_LIMIT)
    ics_url = None
    if token_secret:
        token = calendar_token(
            token_secret, calendar_payload(worksheet_id, channel, ts)
        )
        query = urlencode({"token": token, "channel": channel, "ts": ts})
        ics_url = f"{public_base_url}/bigchat/{worksheet_id}/event.ics?{query}"
    return registration_blocks(msg, gcal_url, ics_url)


def load_calendar_context(
    worksheet_id,
    channel,
    ts,
    token,
    *,
    token_secret,
    sheets_factory,
    web_client_factory,
):
    if not token_secret:
        raise CalendarUnavailable()
    if not verify_calendar_token(
        token_secret, calendar_payload(worksheet_id, channel, ts), token
    ):
        raise CalendarAccessDenied()
    try:
        sheet_name = sheets_factory().get_worksheet_title(worksheet_id)
    except Exception as ex:
        logger.warning(f"Failed to load worksheet {worksheet_id}: {ex}")
        raise CalendarUnavailable() from ex
    event = parse_sheet_name(sheet_name or "")
    if not event:
        raise CalendarUnavailable()
    return event, _build_calendar_description(channel, ts, web_client_factory)


def _fetch_bigchat_intro(channel, ts, web_client_factory):
    if not channel or not ts:
        return ""
    try:
        resp = web_client_factory().conversations_replies(
            channel=channel, ts=ts, limit=1
        )
        return resp["messages"][0]["text"]
    except Exception as ex:
        logger.warning(f"Failed to fetch bigchat intro: {ex}")
        return ""


def _fetch_permalink(channel, ts, web_client_factory):
    if not channel or not ts:
        return ""
    try:
        return web_client_factory().chat_getPermalink(channel=channel, message_ts=ts)[
            "permalink"
        ]
    except Exception as ex:
        logger.warning(f"Failed to fetch permalink: {ex}")
        return ""


def _build_calendar_description(channel, ts, web_client_factory):
    parts = []
    permalink = _fetch_permalink(channel, ts, web_client_factory)
    if permalink:
        parts.append(f"슬랙에서 소개글 보기: {permalink}")
    intro = _fetch_bigchat_intro(channel, ts, web_client_factory)
    if intro:
        parts.append(intro)
    return "\n\n".join(parts)
