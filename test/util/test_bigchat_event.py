import unittest

from util.bigchat_event import (
    ics_token,
    parse_sheet_name,
    to_gcal_link,
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

    def test_ics(self):
        ics = to_ics(self.event, uid="bigchat-123@ausg-anna")

        assert "BEGIN:VCALENDAR" in ics
        assert "UID:bigchat-123@ausg-anna" in ics
        assert "DTSTART:20260820T100000Z" in ics  # KST 19:00 = UTC 10:00
        assert "DTEND:20260820T120000Z" in ics
        assert "SUMMARY:AI meetup" in ics

    def test_ics_escapes_special_chars(self):
        event = parse_sheet_name("반가워, AUSG; friends 26-08-20 19:00~21:00")

        ics = to_ics(event, uid="uid")

        assert "SUMMARY:반가워\\, AUSG\\; friends" in ics


class TestIcsToken(unittest.TestCase):
    def test_verify_roundtrip(self):
        token = ics_token("secret", 161837744)

        assert verify_ics_token("secret", 161837744, token) is True
        assert verify_ics_token("secret", 161837745, token) is False
        assert verify_ics_token("other-secret", 161837744, token) is False
        assert verify_ics_token("secret", 161837744, "") is False
