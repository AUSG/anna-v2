from types import SimpleNamespace
from unittest.mock import patch

import pytest

from handler.bigchat import abandon_bigchat, join_bigchat
from handler.bigchat.abandon_bigchat import AbandonBigchat
from handler.bigchat.abandon_bigchat import SPREADSHEET_PAT as ABANDON_SPREADSHEET_PAT
from handler.bigchat.join_bigchat import JoinBigchat
from handler.bigchat.join_bigchat import SPREADSHEET_PAT as JOIN_SPREADSHEET_PAT
from handler.bigchat.sheet_link import SPREADSHEET_PAT, extract_worksheet_id


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


@pytest.mark.parametrize(
    "module, handler",
    [(join_bigchat, JoinBigchat), (abandon_bigchat, AbandonBigchat)],
)
def test_compatibility_delegate_passes_texts_and_returns_zero(module, handler):
    messages = [SimpleNamespace(text="소개글"), SimpleNamespace(text="신청 시트")]

    with patch.object(module, "extract_worksheet_id", return_value=0) as extract:
        result = handler._extract_worksheet_id(messages)

    extract.assert_called_once()
    assert extract.call_args.kwargs == {}
    (texts,) = extract.call_args.args
    assert list(texts) == ["소개글", "신청 시트"]
    assert result is extract.return_value


@pytest.mark.parametrize(
    "module, handler",
    [(join_bigchat, JoinBigchat), (abandon_bigchat, AbandonBigchat)],
)
@pytest.mark.parametrize("failure", [ValueError("잘못된 시트 ID"), TypeError("잘못된 메시지 텍스트")])
def test_compatibility_delegate_propagates_helper_error(module, handler, failure):
    with patch.object(module, "extract_worksheet_id", side_effect=failure) as extract:
        with pytest.raises(type(failure)) as error:
            handler._extract_worksheet_id([SimpleNamespace(text="소개글")])

    extract.assert_called_once()
    assert error.value is failure


def test_extract_worksheet_id_does_not_consume_later_texts():
    def texts():
        yield "https://docs.google.com/spreadsheets/d/a/edit#gid=12"
        raise AssertionError("첫 일치 뒤에는 순회하지 않아야 한다")

    assert extract_worksheet_id(texts()) == 12


@pytest.mark.parametrize("handler", [JoinBigchat, AbandonBigchat])
def test_compatibility_delegate_does_not_read_later_messages(handler):
    messages = [
        SimpleNamespace(text="https://docs.google.com/spreadsheets/d/a/edit#gid=12"),
        object(),
    ]

    assert handler._extract_worksheet_id(messages) == 12


@pytest.mark.parametrize("handler", [JoinBigchat, AbandonBigchat])
def test_compatibility_delegate_preserves_missing_text_error(handler):
    with pytest.raises(AttributeError) as error:
        handler._extract_worksheet_id([object()])

    assert str(error.value) == "'object' object has no attribute 'text'"


def test_pattern_is_explicitly_reexported():
    assert JOIN_SPREADSHEET_PAT is SPREADSHEET_PAT
    assert ABANDON_SPREADSHEET_PAT is SPREADSHEET_PAT
    assert SPREADSHEET_PAT.pattern == (
        r"https://docs.google.com/spreadsheets/d/.*/edit#gid=(\d*)"
    )
    assert SPREADSHEET_PAT.flags == 32
