import pytest

from features.bigchat.services.sheet_link import extract_worksheet_id


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
        (
            [
                "https://docs.google.com/spreadsheets/d/a/edit#gid=12",
                "https://docs.google.com/spreadsheets/d/b/edit#gid=34",
            ],
            12,
        ),
    ],
)
def test_extract_worksheet_id_from_text_iterable(texts, expected):
    assert extract_worksheet_id(iter(texts)) == expected
