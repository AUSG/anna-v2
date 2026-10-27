import copy

import pytest

from features.questions.models import ChatResult, Source, select_conversation


def test_empty_conversation_has_no_turns():
    assert select_conversation([], "질문") == []


def test_relevance_priority_and_recent_budget():
    turns = [
        {"role": "user", "content": "무" * 4000, "timestamp": str(index)}
        for index in range(12)
    ]
    turns[3]["content"] = "Kubernetes" + "가" * 3990
    before = copy.deepcopy(turns)

    selected = select_conversation(turns, "KUBERNETES 일정")

    assert [turn["timestamp"] for turn in selected] == [
        "0",
        "3",
        "4",
        "5",
        "6",
        "7",
        "8",
        "9",
        "10",
        "11",
    ]
    assert turns == before


def test_over_budget_candidate_does_not_prevent_a_later_smaller_turn():
    root = {"role": "user", "content": "r" * 4000}
    small = {"role": "user", "content": "s" * 1000}
    relevant = [{"role": "user", "content": "tag" + "가" * 3997} for _ in range(8)] + [
        {"role": "user", "content": "tag" + "나" * 2997}
    ]
    newest = {"role": "user", "content": "x" * 4000}
    turns = [root, small, *relevant, newest]

    selected = select_conversation(turns, "tag")

    assert selected == turns[:-1]
    assert sum(len(turn["content"]) for turn in selected) == 40000


def test_conversation_respects_message_limit():
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
    ],
)
def test_relevant_turn_is_selected_before_recent_turn(
    question, middle, selected_index, monkeypatch
):
    monkeypatch.setattr("features.questions.models.MAX_CONVERSATION_MESSAGES", 2)
    turns = [
        {"role": "user", "content": "root"},
        {"role": "user", "content": middle},
        {"role": "user", "content": "newest"},
    ]

    assert select_conversation(turns, question) == [turns[0], turns[selected_index]]


def test_default_collections_are_not_shared():
    source, other_source = Source("doc"), Source("other")
    result, other_result = ChatResult("답변"), ChatResult("다른 답변")

    source.evidence_urls.append("https://example.test/evidence")
    result.sources.append(source)
    result.timing["search_ms"] = 2.5
    result.citations.append("doc")

    assert other_source.evidence_urls == []
    assert other_result.sources == []
    assert other_result.timing == {}
    assert other_result.citations == []
