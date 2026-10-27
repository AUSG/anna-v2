import copy
from dataclasses import MISSING, fields
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional, get_type_hints

import pytest

from features.questions.models import (
    MAX_CONVERSATION_AUTHOR_CHARS,
    MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_MESSAGE_CHARS,
    MAX_CONVERSATION_MESSAGES,
    MAX_CONVERSATION_TIMESTAMP_CHARS,
    ChatResult,
    Source,
)
from features.questions.services.conversation import select_conversation


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
        "features.questions.services.conversation.MAX_CONVERSATION_MESSAGES", 2
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


def test_shared_limits_keep_the_crawler_contract():
    assert (
        MAX_CONVERSATION_MESSAGES,
        MAX_CONVERSATION_MESSAGE_CHARS,
        MAX_CONVERSATION_CHARS,
        MAX_CONVERSATION_AUTHOR_CHARS,
        MAX_CONVERSATION_TIMESTAMP_CHARS,
    ) == (100, 4000, 40000, 200, 100)


def test_source_fields_keep_order_defaults_and_list_factory():
    source_fields = fields(Source)
    assert [(item.name, item.default) for item in source_fields] == [
        ("document_id", MISSING),
        ("score", 0.0),
        ("title", ""),
        ("url", ""),
        ("content_preview", ""),
        ("channel_id", None),
        ("thread_ts", None),
        ("user_id", None),
        ("timestamp", None),
        ("truncated", False),
        ("evidence_urls", MISSING),
    ]
    assert all(item.default_factory is MISSING for item in source_fields[:-1])
    assert source_fields[-1].default_factory is list


def test_chat_result_fields_keep_order_defaults_and_collection_factories():
    result_fields = fields(ChatResult)
    assert [(item.name, item.default) for item in result_fields] == [
        ("answer", MISSING),
        ("sources", MISSING),
        ("timing", MISSING),
        ("status", "answered"),
        ("citations", MISSING),
        ("trace_id", ""),
    ]
    assert [item.default_factory for item in result_fields] == [
        MISSING,
        list,
        dict,
        MISSING,
        list,
        MISSING,
    ]


def test_value_types_stay_mutable_with_independent_default_collections():
    source, other_source = Source("doc"), Source("other")
    result, other_result = ChatResult("답변"), ChatResult("다른 답변")

    assert Source.__dataclass_params__.frozen is False
    assert ChatResult.__dataclass_params__.frozen is False
    source.title = "변경된 제목"
    source.evidence_urls.append("https://example.test/evidence")
    result.answer = "변경된 답변"
    result.sources.append(source)
    result.timing["search_ms"] = 2.5
    result.citations.append("doc")

    assert source.title == "변경된 제목"
    assert result.answer == "변경된 답변"
    assert result.sources[0] is source
    assert other_source.evidence_urls == []
    assert other_result.sources == []
    assert other_result.timing == {}
    assert other_result.citations == []


def test_runtime_type_hints_resolve_application_values():
    assert get_type_hints(Source) == {
        "document_id": str,
        "score": float,
        "title": str,
        "url": str,
        "content_preview": str,
        "channel_id": Optional[str],
        "thread_ts": Optional[str],
        "user_id": Optional[str],
        "timestamp": Optional[str],
        "truncated": bool,
        "evidence_urls": List[str],
    }
    assert get_type_hints(ChatResult) == {
        "answer": str,
        "sources": List[Source],
        "timing": Dict[str, Any],
        "status": str,
        "citations": List[str],
        "trace_id": str,
    }
    assert get_type_hints(select_conversation) == {
        "normalized": List[Dict[str, str]],
        "question": str,
        "return": List[Dict[str, str]],
    }


def test_application_import_is_isolated_in_a_fresh_stdlib_only_process(tmp_path):
    root = Path(__file__).resolve().parents[4]
    code = r"""
import importlib.abc
import json
from pathlib import Path
import socket
import sys
import threading
from typing import get_type_hints

root = Path(sys.argv[1]).resolve()
blocked = {
    "handler", "implementation", "integrations", "bootstrap", "app", "anna", "config", "requests", "dotenv",
    "slack_sdk", "slack_bolt", "gspread", "gspread_formatting", "google",
    "google_auth_oauthlib", "pydantic", "pydantic_settings", "flask", "gunicorn",
}
assert not [name for name in sys.modules if name.split(".")[0] in blocked]
attempts = []

class BlockAdapters(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            attempts.append(fullname)
            raise AssertionError("forbidden application import: " + fullname)

sys.meta_path.insert(0, BlockAdapters())

def forbidden(*args, **kwargs):
    raise AssertionError("network and scheduler threads are forbidden")

socket.socket.connect = socket.socket.connect_ex = forbidden
socket.create_connection = socket.getaddrinfo = forbidden
threading.Thread.start = forbidden

def forbid_credentials(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if (root / "src/env") == path or (root / "src/env") in path.parents:
            raise AssertionError("environment or credentials read: " + str(path))
        if path.name == ".env" or path.suffix == ".pem" or "credential" in path.name.lower():
            raise AssertionError("environment or credentials read: " + str(path))

sys.addaudithook(forbid_credentials)
sys.path.insert(0, str(root / "src"))
from features.questions import models as question
from features.questions.services import conversation

expected = root / "src/features/questions/models.py"
assert Path(question.__file__).resolve() == expected
assert Path(conversation.select_conversation.__code__.co_filename).resolve() == root / "src/features/questions/services/conversation.py"
assert question.Source.__module__ == "features.questions.models"
assert question.ChatResult.__module__ == "features.questions.models"
assert get_type_hints(question.ChatResult)["sources"].__args__[0] is question.Source
turn = {"role": "user", "content": "질문"}
assert conversation.select_conversation([turn], "질문")[0] is turn
assert question.ChatResult("답변").sources == []
loaded = sorted(name for name in sys.modules if name.split(".")[0] in blocked)
assert attempts == []
assert loaded == []
print(json.dumps({"source": str(expected), "blocked_loaded": loaded, "attempts": attempts}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", code, str(root)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout) == {
        "source": str(root / "src/features/questions/models.py"),
        "blocked_loaded": [],
        "attempts": [],
    }
