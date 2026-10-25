import copy

import pytest

from handler.bigchat.question_conversation import select_conversation


def test_empty_conversation_has_no_turns():
    assert select_conversation([], "질문") == []


@pytest.mark.parametrize(
    ("relevant_index", "question", "timestamps"),
    [
        (3, "KUBERNETES 일정", ["0", "3", "4", "5", "6", "7", "8", "9", "10", "11"]),
        (11, "Kubernetes", ["0", "4", "5", "6", "7", "8", "9", "10", "11"]),
    ],
    ids=["middle", "recent"],
)
def test_relevance_priority_and_recent_budget(relevant_index, question, timestamps):
    turns = [
        {"role": "user", "content": "무" * 4000, "timestamp": str(index)}
        for index in range(12)
    ]
    turns[relevant_index]["content"] = "Kubernetes" + "가" * 3990
    before = copy.deepcopy(turns)

    selected = select_conversation(turns, question)

    assert [turn["timestamp"] for turn in selected] == timestamps
    assert turns == before
    assert all(turn is turns[int(turn["timestamp"])] for turn in selected)


def test_equal_dicts_are_not_the_same_selected_object():
    root = {"role": "user", "content": "같음"}
    twin = dict(root)
    turns = [root, twin] + [
        {"role": "user", "content": str(index)} for index in range(99)
    ]

    selected = select_conversation(turns, "!")

    assert len(selected) == 100
    assert selected[0] is root
    assert all(turn is not twin for turn in selected)
    assert selected[1:] == turns[2:]


def test_repeated_input_reference_is_retained_at_each_input_position():
    shared = {"role": "user", "content": "동일 객체"}
    last = {"role": "assistant", "content": "마지막"}

    selected = select_conversation([shared, shared, last], "동일")

    assert len(selected) == 3
    assert selected[0] is shared
    assert selected[1] is shared
    assert selected[2] is last


def test_over_budget_candidate_does_not_prevent_a_later_smaller_turn():
    root = {"role": "user", "content": "r" * 4000}
    small = {"role": "user", "content": "s" * 1000}
    relevant = [{"role": "user", "content": "tag" + "가" * 3997} for _ in range(8)] + [
        {"role": "user", "content": "tag" + "나" * 2997}
    ]
    newest = {"role": "user", "content": "x" * 4000}
    turns = [root, small, *relevant, newest]

    selected = select_conversation(turns, "tag")

    assert len(selected) == 11
    assert all(left is right for left, right in zip(selected, turns[:-1]))
    assert sum(len(turn["content"]) for turn in selected) == 40000


def test_message_count_limit_is_applied_before_identity_filtering():
    turns = [
        {"role": "user", "content": "aa", "timestamp": str(index)}
        for index in range(120)
    ]

    selected = select_conversation(turns, "aa")

    assert [turn["timestamp"] for turn in selected] == [str(i) for i in range(100)]


@pytest.mark.parametrize(
    ("question", "middle", "selected_index"),
    [
        ("AB", "ab", 1),
        ("가나", "가나", 1),
        ("12", "12", 1),
        ("a", "a", 2),
        ("😀", "😀", 2),
        ("ㄱㄱ", "ㄱㄱ", 2),
        ("éé", "éé", 2),
        ("ＡＢ", "ＡＢ", 2),
        ("e\u0301e\u0301", "e\u0301e\u0301", 2),
    ],
)
def test_relevance_uses_existing_two_character_term_pattern(
    question, middle, selected_index, monkeypatch
):
    monkeypatch.setattr(
        "handler.bigchat.question_conversation.MAX_CONVERSATION_MESSAGES", 2
    )
    turns = [
        {"role": "user", "content": "root"},
        {"role": "user", "content": middle},
        {"role": "user", "content": "newest"},
    ]

    selected = select_conversation(turns, question)

    assert len(selected) == 2
    assert selected[0] is turns[0]
    assert selected[1] is turns[selected_index]
