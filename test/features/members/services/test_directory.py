from unittest.mock import MagicMock

from features.members.models import Member
from features.members.services.directory import (
    MEMBER_INFO_COLUMNS,
    MemberManager,
    build_members,
)
from shared.gateways import SheetsGateway

WORKSHEET_ID = 7
HEADER = ["user_id", "kor_name", "eng_name", "email", "phone", "school"]
ROWS = [
    HEADER,
    ["U0001", "김철수", "Kim Chulsoo", "Chulsoo@Example.com", "010-1234-5678", "AUSG대"],
    ["U0002", "박영희", "Park Younghee", "", "010-2345-6789", "AUSG사"],  # 이메일 없음
    ["U0003", "이몽룡"],  # 값 누락 행 (스킵됨)
]


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _make(rows=ROWS, *, ttl_sec=60, clock=None):
    sheets = MagicMock(spec=SheetsGateway)
    sheets.get_values.return_value = rows
    clock = clock or FakeClock()
    sut = MemberManager(sheets, WORKSHEET_ID, ttl_sec=ttl_sec, clock=clock)
    return sut, sheets, clock


def test_maps_normalized_email_to_slack_id():
    sut, sheets, _ = _make()

    mapping = sut.email_to_slack_ids()

    assert mapping == {"chulsoo@example.com": "U0001"}
    sheets.get_values.assert_called_once_with(WORKSHEET_ID, MEMBER_INFO_COLUMNS)


def test_email_mapping_strips_surrounding_whitespace():
    sut, _, _ = _make(
        [HEADER, ["U1", "가", "A", "  Me@Example.com \t", "010-0000-0000", "학교"]]
    )
    assert sut.email_to_slack_ids() == {"me@example.com": "U1"}


def test_find_returns_member_for_known_user():
    sut, _, _ = _make()

    assert sut.find("U0001") == Member(
        kor_name="김철수",
        eng_name="Kim Chulsoo",
        email="Chulsoo@Example.com",
        phone="010-1234-5678",
        school_name_or_company_name="AUSG대",
    )
    assert sut.find("U0001").is_complete()


def test_find_returns_none_for_unknown_or_skipped_user():
    sut, _, _ = _make()

    assert sut.find("U9999") is None
    # 값이 누락된 행은 등록되지 않는다
    assert sut.find("U0003") is None


def test_worksheet_id_is_coerced_to_int():
    sheets = MagicMock(spec=SheetsGateway)
    sheets.get_values.return_value = ROWS
    MemberManager(sheets, "7").find("U0001")
    sheets.get_values.assert_called_once_with(7, MEMBER_INFO_COLUMNS)


def test_cache_is_shared_within_ttl():
    sut, sheets, clock = _make(ttl_sec=60)

    sut.find("U0001")
    sut.find("U0002")
    sut.email_to_slack_ids()
    clock.advance(59.9)
    sut.find("U0001")

    sheets.get_values.assert_called_once_with(WORKSHEET_ID, MEMBER_INFO_COLUMNS)


def test_cache_is_refreshed_after_ttl():
    sut, sheets, clock = _make(ttl_sec=60)
    assert sut.find("U0004") is None

    sheets.get_values.return_value = ROWS + [
        ["U0004", "성춘향", "Sung Chunhyang", "chun@example.com", "010-3456-7890", "남원"]
    ]
    clock.advance(59)
    assert sut.find("U0004") is None  # 아직 ttl 안
    clock.advance(1)

    member = sut.find("U0004")

    assert member is not None and member.kor_name == "성춘향"
    assert sheets.get_values.call_count == 2
    assert sut.email_to_slack_ids() == {
        "chulsoo@example.com": "U0001",
        "chun@example.com": "U0004",
    }
    assert sheets.get_values.call_count == 2


def test_cache_refresh_resets_the_ttl_window():
    sut, sheets, clock = _make(ttl_sec=10)
    sut.find("U0001")
    clock.advance(10)
    sut.find("U0001")
    clock.advance(9)
    sut.find("U0001")
    assert sheets.get_values.call_count == 2
    clock.advance(1)
    sut.find("U0001")
    assert sheets.get_values.call_count == 3


def test_build_members_skips_header_empty_and_short_rows():
    members = build_members(
        [
            HEADER,
            [],
            ["U0003", "이몽룡"],
            ["U0005", "가", "A", "a@example.com", "010-0000-0000"],  # 5열: 학교 누락
            ["U0006", "나", "B", "b@example.com", "010-0000-0001", "학교", "추가열"],
        ]
    )
    assert members == {
        "U0006": Member(
            kor_name="나",
            eng_name="B",
            email="b@example.com",
            phone="010-0000-0001",
            school_name_or_company_name="학교",
        )
    }


def test_build_members_with_only_header_is_empty():
    assert build_members([HEADER]) == {}
    assert build_members([]) == {}
