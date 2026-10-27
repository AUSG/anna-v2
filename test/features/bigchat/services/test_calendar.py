from unittest.mock import MagicMock

import pytest

from features.bigchat.services.calendar import BigchatCalendar, CalendarNotFound

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"


def make_calendar():
    title = MagicMock(return_value=SHEET_NAME)
    permalink = MagicMock(return_value="https://slack.test/intro")
    intro = MagicMock(return_value="소개글")
    return BigchatCalendar(title, permalink, intro), title, permalink, intro


def test_loads_event_and_description_in_order():
    calendar, title, permalink, intro = make_calendar()
    trace = MagicMock()
    for name, mock in (("title", title), ("permalink", permalink), ("intro", intro)):
        trace.attach_mock(mock, name)
    event, description = calendar.load(123, "C1", "1.0")
    assert event.name == "AI 밋업"
    assert description == "슬랙에서 소개글 보기: https://slack.test/intro\n\n소개글"
    assert [call[0] for call in trace.mock_calls] == ["title", "permalink", "intro"]


@pytest.mark.parametrize("channel,ts", [("", ""), ("C1", ""), ("", "1.0")])
def test_missing_slack_context_skips_optional_lookups(channel, ts):
    calendar, _, permalink, intro = make_calendar()
    _, description = calendar.load(123, channel, ts)
    assert description == ""
    permalink.assert_not_called()
    intro.assert_not_called()


@pytest.mark.parametrize("failure", ["title", "invalid", "missing"])
def test_missing_calendar_does_not_fetch_slack(failure):
    calendar, title, permalink, intro = make_calendar()
    if failure == "title":
        title.side_effect = RuntimeError("sheet unavailable")
    else:
        title.return_value = None if failure == "missing" else "구형식 시트"
    with pytest.raises(CalendarNotFound):
        calendar.load(123, "C1", "1.0")
    permalink.assert_not_called()
    intro.assert_not_called()


@pytest.mark.parametrize("failure", ["permalink", "intro", "both"])
def test_optional_lookup_failures_preserve_remaining_description(failure):
    calendar, _, permalink, intro = make_calendar()
    if failure in ("permalink", "both"):
        permalink.side_effect = RuntimeError("link unavailable")
    if failure in ("intro", "both"):
        intro.side_effect = RuntimeError("intro unavailable")
    event, description = calendar.load(123, "C1", "1.0")
    assert event.name == "AI 밋업"
    assert (
        description
        == {
            "permalink": "소개글",
            "intro": "슬랙에서 소개글 보기: https://slack.test/intro",
            "both": "",
        }[failure]
    )
    permalink.assert_called_once_with("C1", "1.0")
    intro.assert_called_once_with("C1", "1.0")
