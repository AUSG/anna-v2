import unittest

from util.bigchat_event import (
    SLACK_BUTTON_URL_LIMIT,
    ics_payload,
    ics_token,
    parse_sheet_name,
    to_gcal_link,
    to_gcal_link_truncated,
    to_ics,
    verify_ics_token,
)


class TestParseSheetName(unittest.TestCase):
    def test_valid(self):
        event = parse_sheet_name("AI 밋업 26-08-20 19:00~21:00")

        assert event is not None
        assert event.name == "AI 밋업"
        assert event.start.strftime("%Y-%m-%d %H:%M") == "2026-08-20 19:00"
        assert event.end.strftime("%Y-%m-%d %H:%M") == "2026-08-20 21:00"

    def test_invalid_format(self):
        for sheet_name in [
            "빅챗 23-07-31",  # 시간 없음 (구형식)
            "AI 밋업 2026-08-20 19:00~21:00",  # yyyy
            "AI 밋업 26-08-20 19:00-21:00",  # ~ 대신 -
            "26-08-20 19:00~21:00",  # 이름 없음
            "",
        ]:
            assert parse_sheet_name(sheet_name) is None, sheet_name

    def test_nonexistent_datetime_rejected(self):
        assert parse_sheet_name("AI 밋업 26-02-30 19:00~21:00") is None  # 2/30
        assert parse_sheet_name("AI 밋업 26-08-20 25:00~26:00") is None  # 25시

    def test_end_not_after_start_rejected(self):
        assert parse_sheet_name("AI 밋업 26-08-20 21:00~19:00") is None
        assert parse_sheet_name("AI 밋업 26-08-20 19:00~19:00") is None


class TestCalendarLinks(unittest.TestCase):
    def setUp(self):
        self.event = parse_sheet_name("AI meetup 26-08-20 19:00~21:00")

    def test_gcal_link(self):
        link = to_gcal_link(self.event)

        assert link.startswith("https://calendar.google.com/calendar/render?")
        assert "action=TEMPLATE" in link
        assert "text=AI+meetup" in link
        assert "dates=20260820T190000%2F20260820T210000" in link
        assert "ctz=Asia%2FSeoul" in link

    def test_gcal_link_with_details(self):
        link = to_gcal_link(self.event, details="이번 빅챗은 강남에서 합니다")

        assert "details=" in link

    def test_gcal_link_truncated_fits_slack_button_limit(self):
        long_intro = "빅챗 소개글 " * 2000

        link = to_gcal_link_truncated(self.event, long_intro)

        assert len(link) <= SLACK_BUTTON_URL_LIMIT
        assert "details=" in link  # 잘리더라도 앞부분은 남는다

    def test_ics(self):
        ics = to_ics(self.event, uid="bigchat-123@ausg-anna")

        assert "BEGIN:VCALENDAR" in ics
        assert "UID:bigchat-123@ausg-anna" in ics
        assert "DTSTART:20260820T100000Z" in ics  # KST 19:00 = UTC 10:00
        assert "DTEND:20260820T120000Z" in ics
        assert "SUMMARY:AI meetup" in ics
        assert "DESCRIPTION" not in ics  # 소개글 없으면 필드 생략

    def test_ics_with_description(self):
        ics = to_ics(self.event, uid="uid", description="이번 빅챗은\n강남에서 합니다")

        assert "DESCRIPTION:이번 빅챗은\\n강남에서" in ics.replace("\r\n ", "")

    def test_ics_escapes_special_chars(self):
        event = parse_sheet_name("반가워, AUSG; friends 26-08-20 19:00~21:00")

        ics = to_ics(event, uid="uid")

        assert "SUMMARY:반가워\\, AUSG\\; friends" in ics.replace("\r\n ", "")

    def test_ics_folds_long_lines(self):
        ics = to_ics(self.event, uid="uid", description="가나다라마바사아자차카타파하 " * 30)

        for line in ics.split("\r\n"):
            assert len(line.encode("utf-8")) <= 75, line


class TestIcsToken(unittest.TestCase):
    def test_verify_roundtrip(self):
        payload = ics_payload(161837744, "C03SZTDEDK3", "1688801145.307229")
        token = ics_token("secret", payload)

        assert verify_ics_token("secret", payload, token) is True
        assert verify_ics_token("other-secret", payload, token) is False
        assert verify_ics_token("secret", payload, "") is False
        # channel/ts가 바뀌면 (다른 스레드로 바꿔치기) 검증 실패
        tampered = ics_payload(161837744, "C_OTHER", "1688801145.307229")
        assert verify_ics_token("secret", tampered, token) is False
