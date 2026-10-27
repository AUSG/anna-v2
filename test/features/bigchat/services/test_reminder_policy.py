import importlib
from typing import get_type_hints

import pytest

from features.bigchat.models import ReminderResult
from features.bigchat.services.reminder_policy import applicant_email, select_bigchats


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
        (["a@@b.c"], "a@@b.c"),
        (["first@example.com", None], "first@example.com"),
    ],
)
def test_applicant_email_uses_only_the_first_matching_cell(row, expected):
    before = list(row)
    assert applicant_email(row) == expected
    assert row == before


@pytest.mark.parametrize("cell", [None, 17])
def test_applicant_email_keeps_invalid_cell_errors(cell):
    with pytest.raises(AttributeError):
        applicant_email(["not email", cell, "valid@example.com"])


def test_applicant_email_keeps_invalid_row_error():
    with pytest.raises(TypeError):
        applicant_email(None)


def test_reminder_exports_and_runtime_type_hints_share_application_identity():
    reminder = importlib.import_module("features.bigchat.services.reminders")
    messages = importlib.import_module("features.bigchat.presentation.reminders")
    policy = importlib.import_module("features.bigchat.services.reminder_policy")
    for module in (reminder, messages):
        assert module.ReminderResult is ReminderResult
    assert reminder.select_bigchats is policy.select_bigchats is select_bigchats
    assert select_bigchats.__module__ == "features.bigchat.services.reminder_policy"
    assert get_type_hints(reminder.RemindBigchat.run)["return"] is ReminderResult
    for method in (reminder.RemindBigchat._remind_applicants, messages.build_report):
        assert get_type_hints(method)["result"] is ReminderResult
