import pytest

from features.bigchat import slack as bigchat_slack
from features.bigchat.services.sheet_link import SPREADSHEET_PAT, extract_worksheet_id


@pytest.mark.parametrize(
    "texts, expected",
    [
        ([], None),
        (["", "새로운 빅챗을 모집합니다!"], None),
        (["https://example.com/edit#gid=12"], None),
        (["http://docs.google.com/spreadsheets/d/a/edit#gid=12"], None),
        (["https://docs.google.com/spreadsheets/d/a/edit?gid=12"], None),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=12"], 12),
        (["<https://docs.google.com/spreadsheets/d/a/edit#gid=12|시트>"], 12),
        (["소개글", "https://docs.google.com/spreadsheets/d/a/edit#gid=12"], 12),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=0"], 0),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=00012"], 12),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=12abc"], 12),
        (["https://docs.google.com/spreadsheets/d//edit#gid=12"], 12),
        (["https://docsXgoogleYcom/spreadsheets/d/a/edit#gid=12"], 12),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=١٢"], 12),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=１２"], 12),
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=12 "
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34"
            ],
            34,
        ),
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=12\n"
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34"
            ],
            12,
        ),
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=12\u2028"
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34"
            ],
            34,
        ),
        (["https://docs.google.com/spreadsheets/d/a\n/edit#gid=12"], None),
        (["https://docs.google.com/spreadsheets/d/a\r/edit#gid=12"], 12),
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=12",
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34",
            ],
            12,
        ),
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=0",
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34",
            ],
            0,
        ),
        (["https://docs.google.com/spreadsheets/d/a/edit#gid=12", None], 12),
    ],
)
def test_extract_worksheet_id_from_text_iterable(texts, expected):
    assert extract_worksheet_id(iter(texts)) == expected


@pytest.mark.parametrize(
    "texts, error_type, error_message",
    [
        (
            ["https://docs.google.com/spreadsheets/d/a/edit#gid="],
            ValueError,
            "invalid literal for int() with base 10: ''",
        ),
        (
            ["https://docs.google.com/spreadsheets/d/a/edit#gid=abc"],
            ValueError,
            "invalid literal for int() with base 10: ''",
        ),
        (
            ["https://docs.google.com/spreadsheets/d/a/edit#gid=-12"],
            ValueError,
            "invalid literal for int() with base 10: ''",
        ),
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=",
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34",
            ],
            ValueError,
            "invalid literal for int() with base 10: ''",
        ),
        ([None], TypeError, "expected string or bytes-like object, got 'NoneType'"),
        ([12], TypeError, "expected string or bytes-like object, got 'int'"),
        ([[]], TypeError, "expected string or bytes-like object, got 'list'"),
        (
            [b"https://docs.google.com/spreadsheets/d/a/edit#gid=12"],
            TypeError,
            "cannot use a string pattern on a bytes-like object",
        ),
    ],
)
def test_extract_worksheet_id_preserves_errors(texts, error_type, error_message):
    with pytest.raises(error_type) as error:
        extract_worksheet_id(iter(texts))
    assert str(error.value) == error_message


def test_extract_worksheet_id_does_not_consume_later_texts():
    def texts():
        yield "https://docs.google.com/spreadsheets/d/a/edit#gid=12"
        raise AssertionError("첫 일치 뒤에는 순회하지 않아야 한다")

    assert extract_worksheet_id(texts()) == 12


def test_reaction_handlers_use_the_shared_parser_and_pattern():
    """참여/취소 반응 처리(features/bigchat/slack.py)는 같은 파서로 스레드에서 시트 ID 를 찾는다."""
    assert bigchat_slack.extract_worksheet_id is extract_worksheet_id
    assert SPREADSHEET_PAT.pattern == (
        r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
    )
    assert SPREADSHEET_PAT.flags == 32
