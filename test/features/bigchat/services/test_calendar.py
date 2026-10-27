"""캘린더 링크 발급과 ics 다운로드의 검증/조회 경로."""

import hashlib
import hmac
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit

import pytest

from features.bigchat.models import (
    CalendarContext,
    CalendarFailure,
    CalendarLinks,
    parse_sheet_name,
)
from features.bigchat.services.calendar import (
    SLACK_BUTTON_URL_LIMIT,
    calendar_links,
    calendar_payload,
    calendar_token,
    load_calendar_context,
)
from shared.gateways import SheetsGateway
from shared.slack_models import Message
from test.fixtures.runtime import fake_slack

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"
EVENT = parse_sheet_name(SHEET_NAME)
WORKSHEET_ID = 161837744
CHANNEL = "C03SZTDEDK3"
TS = "1688801145.307229"
PERMALINK = "https://ausg.slack.com/archives/C03SZTDEDK3/p1688801145307229"
INTRO = "이번 빅챗 소개글입니다"
SECRET = "testsecret"
BASE_URL = "https://anna.test"
TOKEN = hmac.new(
    SECRET.encode(), f"{WORKSHEET_ID}:{CHANNEL}:{TS}".encode(), hashlib.sha256
).hexdigest()


def _query(url):
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def _links(permalink=PERMALINK, intro=INTRO, *, token_secret=SECRET):
    return calendar_links(
        EVENT,
        WORKSHEET_ID,
        CHANNEL,
        TS,
        permalink,
        intro,
        public_base_url=BASE_URL,
        token_secret=token_secret,
    )


# --- calendar_links ------------------------------------------------------------------


def test_gcal_is_a_direct_template_link_with_permalink_first_in_details():
    """서버 302 를 거치면 모바일 앱 핸드오프가 끊기므로 캘린더 템플릿 URL 직링크여야 한다."""
    links = _links()

    assert links.gcal_url.startswith("https://calendar.google.com/calendar/render?")
    assert _query(links.gcal_url) == {
        "action": "TEMPLATE",
        "text": "AI 밋업",
        "dates": "20260820T190000/20260820T210000",
        "ctz": "Asia/Seoul",
        "details": f"슬랙에서 소개글 보기: {PERMALINK}\n\n{INTRO}",
    }


def test_gcal_falls_back_to_intro_only_without_permalink():
    assert _query(_links(permalink=None).gcal_url)["details"] == INTRO


def test_gcal_keeps_permalink_when_long_intro_is_truncated():
    links = _links(intro="긴 소개글 " * 2000)

    assert len(links.gcal_url) <= SLACK_BUTTON_URL_LIMIT
    details = _query(links.gcal_url)["details"]
    assert details.startswith(f"슬랙에서 소개글 보기: {PERMALINK}\n\n긴 소개글 ")
    assert details.endswith("…")  # 절단은 뒤에서만 일어난다


def test_ics_link_is_signed_with_hmac_of_worksheet_channel_ts():
    links = _links()

    assert links == CalendarLinks(
        links.gcal_url,
        f"{BASE_URL}/bigchat/{WORKSHEET_ID}/event.ics?token={TOKEN}&channel={CHANNEL}&ts={TS}",
    )
    assert TOKEN == calendar_token(SECRET, calendar_payload(WORKSHEET_ID, CHANNEL, TS))
    assert (
        calendar_payload(WORKSHEET_ID, CHANNEL, TS) == f"{WORKSHEET_ID}:{CHANNEL}:{TS}"
    )


def test_ics_link_is_omitted_without_token_secret():
    links = _links(token_secret="")

    assert links.ics_url is None
    assert links.gcal_url == _links().gcal_url  # gcal 은 비밀값과 무관


# --- load_calendar_context ----------------------------------------------------------------


@pytest.fixture
def sheets():
    gateway = MagicMock(spec=SheetsGateway)
    gateway.get_worksheet_title.return_value = SHEET_NAME
    return gateway


@pytest.fixture
def slack():
    gateway = fake_slack()
    gateway.get_permalink.return_value = PERMALINK
    gateway.get_thread.return_value = [
        Message(
            ts=TS,
            thread_ts=TS,
            channel=CHANNEL,
            user="U01BN035Y6L",
            text="행사 소개글\n둘째 줄",
        ),
        Message(
            ts="1688801200.000000",
            thread_ts=TS,
            channel=CHANNEL,
            user="UANNA",
            text="등록 완료 답글",
        ),
    ]
    return gateway


def _load(sheets, slack, *, channel=CHANNEL, ts=TS, token=TOKEN, token_secret=SECRET):
    return load_calendar_context(
        WORKSHEET_ID,
        channel,
        ts,
        token,
        token_secret=token_secret,
        sheets=sheets,
        slack=slack,
    )


def test_context_has_the_event_and_a_description_of_permalink_and_thread_root(
    sheets, slack
):
    context = _load(sheets, slack)

    assert context == CalendarContext(
        EVENT, f"슬랙에서 소개글 보기: {PERMALINK}\n\n행사 소개글\n둘째 줄"
    )
    sheets.get_worksheet_title.assert_called_once_with(WORKSHEET_ID)
    slack.get_permalink.assert_called_once_with(CHANNEL, TS)
    slack.get_thread.assert_called_once_with(CHANNEL, TS)


def test_unavailable_without_token_secret_before_any_lookup(sheets, slack):
    assert _load(sheets, slack, token_secret="") == CalendarFailure("unavailable")
    assert sheets.mock_calls == []
    assert slack.mock_calls == []


@pytest.mark.parametrize(
    "tampered",
    [
        {"token": ""},
        {
            "token": calendar_token(
                "other-secret", calendar_payload(WORKSHEET_ID, CHANNEL, TS)
            )
        },
        {"channel": "C_OTHER"},  # 다른 스레드로 바꿔치기
        {"ts": "changed"},
    ],
)
def test_denied_on_bad_token_before_any_lookup(sheets, slack, tampered):
    assert _load(sheets, slack, **tampered) == CalendarFailure("denied")
    assert sheets.mock_calls == []
    assert slack.mock_calls == []


@pytest.mark.parametrize("title", [None, "old sheet", "빅챗 23-07-31"])
def test_unavailable_when_worksheet_is_missing_or_not_a_bigchat(sheets, slack, title):
    sheets.get_worksheet_title.return_value = title

    assert _load(sheets, slack) == CalendarFailure("unavailable")
    assert slack.mock_calls == []


def test_unavailable_when_sheet_lookup_fails(sheets, slack):
    sheets.get_worksheet_title.side_effect = RuntimeError("read failed")

    assert _load(sheets, slack) == CalendarFailure("unavailable")
    assert slack.mock_calls == []


@pytest.mark.parametrize(
    ("permalink", "thread", "description"),
    [
        (None, "keep", "행사 소개글\n둘째 줄"),
        (RuntimeError("Slack unavailable"), "keep", "행사 소개글\n둘째 줄"),
        ("keep", [], f"슬랙에서 소개글 보기: {PERMALINK}"),
        ("keep", RuntimeError("Slack unavailable"), f"슬랙에서 소개글 보기: {PERMALINK}"),
        (RuntimeError("Slack unavailable"), RuntimeError("Slack unavailable"), ""),
    ],
)
def test_optional_slack_lookup_failures_do_not_block_the_calendar(
    sheets, slack, permalink, thread, description
):
    if permalink != "keep":
        slack.get_permalink.side_effect = (
            permalink if isinstance(permalink, Exception) else None
        )
        slack.get_permalink.return_value = (
            None if isinstance(permalink, Exception) else permalink
        )
    if thread != "keep":
        slack.get_thread.side_effect = thread if isinstance(thread, Exception) else None
        slack.get_thread.return_value = [] if isinstance(thread, Exception) else thread

    assert _load(sheets, slack) == CalendarContext(EVENT, description)


@pytest.mark.parametrize(("channel", "ts"), [("", TS), (CHANNEL, ""), ("", "")])
def test_description_is_empty_without_a_thread_to_look_up(sheets, slack, channel, ts):
    token = calendar_token(SECRET, calendar_payload(WORKSHEET_ID, channel, ts))

    assert _load(sheets, slack, channel=channel, ts=ts, token=token) == CalendarContext(
        EVENT, ""
    )
    assert slack.mock_calls == []
