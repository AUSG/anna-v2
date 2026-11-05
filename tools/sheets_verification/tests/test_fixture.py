import pytest

from tools.sheets_verification.runner import unsortable_rows_reason


def rows(*names):
    return [
        [name, "company", f"user{i}@example.invalid", "000"]
        for i, name in enumerate(names)
    ]


def test_rows_a_sort_will_move_are_accepted():
    assert unsortable_rows_reason(rows("Charlie", "Alpha", "Bravo")) is None


@pytest.mark.parametrize(
    "names",
    [
        ("Alpha", "Bravo", "Charlie"),  # already ascending
        ("alpha", "Bravo", "charlie"),  # ascending once case is ignored
        ("Bravo", "Alpha", "Alpha"),  # a tie can keep its order
        ("Bravo", "bravo", "Alpha"),  # a tie once case is ignored
    ],
)
def test_rows_a_sort_might_leave_in_place_are_rejected_before_writing(names):
    assert unsortable_rows_reason(rows(*names)) is not None
