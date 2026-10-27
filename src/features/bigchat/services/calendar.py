"""시트 일정과 선택적인 Slack 소개글을 조회한다. HTTP 응답은 만들지 않는다."""

import logging
from typing import Callable

from features.bigchat.calendar import BigchatEvent, parse_sheet_name

logger = logging.getLogger(__name__)


class CalendarNotFound(LookupError):
    pass


class BigchatCalendar:
    def __init__(
        self,
        worksheet_title: Callable[[int], str],
        permalink: Callable[[str, str], str],
        intro: Callable[[str, str], str],
    ):
        self.worksheet_title = worksheet_title
        self.permalink = permalink
        self.intro = intro

    def load(
        self, worksheet_id: int, channel: str = "", ts: str = ""
    ) -> tuple[BigchatEvent, str]:
        try:
            sheet_name = self.worksheet_title(worksheet_id)
        except Exception as ex:
            logger.warning("Failed to load worksheet %s: %s", worksheet_id, ex)
            raise CalendarNotFound(worksheet_id) from ex

        event = parse_sheet_name(sheet_name or "")
        if not event:
            raise CalendarNotFound(worksheet_id)

        return event, self._description(channel, ts)

    def _description(self, channel: str, ts: str) -> str:
        if not channel or not ts:
            return ""
        parts = []
        try:
            permalink = self.permalink(channel, ts)
            if permalink:
                parts.append(f"슬랙에서 소개글 보기: {permalink}")
        except Exception as ex:
            logger.warning("Failed to fetch permalink: %s", ex)
        try:
            intro = self.intro(channel, ts)
            if intro:
                parts.append(intro)
        except Exception as ex:
            # 부가 정보 조회 실패가 캘린더 다운로드를 막지는 않는다.
            logger.warning("Failed to fetch bigchat intro: %s", ex)
        return "\n\n".join(parts)
