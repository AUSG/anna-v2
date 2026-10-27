import pytest

from features.bigchat.services.reminder_policy import applicant_email


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ([], None),
        (["", " \t", "이메일"], None),
        (["김철수", "@drama&company", " Chulsoo@Example.com "], "chulsoo@example.com"),
        (["First@Example.com", "second@example.com"], "first@example.com"),
        (["not an@email.com", "good@example.com"], "good@example.com"),
        (["a@b", "a@b.c", "c@d.e"], "a@b.c"),
        (["두번째@EXAMPLE.COM"], "두번째@example.com"),
        (["\u00a0İ@EXAMPLE.COM\u00a0"], "i\u0307@example.com"),
    ],
)
def test_applicant_email_uses_only_the_first_matching_cell(row, expected):
    assert applicant_email(row) == expected
