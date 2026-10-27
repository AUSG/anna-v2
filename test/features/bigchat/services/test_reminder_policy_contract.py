import subprocess
import sys
from dataclasses import MISSING, fields, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Tuple, get_type_hints

import pytest

from features.bigchat.models import ReminderResult, BigchatEvent
from features.bigchat.services.reminder_policy import select_bigchats
from shared.time import KST


def test_select_bigchats_preserves_sheet_order_and_scan_details():
    worksheets = [
        (9, "MEMBERS_INFO"),
        (4, " 저녁 빅챗 26-08-20 19:00~21:00 "),
        (3, "모레 빅챗 26-08-21 10:00~12:00"),
        (4, "오전 빅챗 26-08-20 10:00~12:00"),
        (5, "빅챗 23-07-31"),
    ]

    matched, parsed, ignored = select_bigchats(worksheets, date(2026, 8, 20))

    assert matched == [
        (
            4,
            BigchatEvent(
                "저녁 빅챗",
                datetime(2026, 8, 20, 19, tzinfo=KST),
                datetime(2026, 8, 20, 21, tzinfo=KST),
            ),
        ),
        (
            4,
            BigchatEvent(
                "오전 빅챗",
                datetime(2026, 8, 20, 10, tzinfo=KST),
                datetime(2026, 8, 20, 12, tzinfo=KST),
            ),
        ),
    ]
    assert parsed == [
        "' 저녁 빅챗 26-08-20 19:00~21:00 ' -> starts 2026-08-20",
        "'모레 빅챗 26-08-21 10:00~12:00' -> starts 2026-08-21",
        "'오전 빅챗 26-08-20 10:00~12:00' -> starts 2026-08-20",
    ]
    assert ignored == ["MEMBERS_INFO", "빅챗 23-07-31"]
    assert worksheets[1] == (4, " 저녁 빅챗 26-08-20 19:00~21:00 ")


def test_select_bigchats_empty():
    assert select_bigchats([], date(2026, 8, 20)) == ([], [], [])


@pytest.mark.parametrize(
    "title",
    [
        "",
        "빅챗 26-02-30 19:00~21:00",
        "빅챗 26-08-20 25:00~26:00",
        "빅챗 26-08-20 21:00~19:00",
        "빅챗 26-08-20 19:00~19:00",
        "줄\n바꿈 26-08-20 19:00~21:00",
    ],
)
def test_select_bigchats_keeps_invalid_titles_in_ignored(title):
    assert select_bigchats([(1, title)], date(2026, 8, 20)) == ([], [], [title])


@pytest.mark.parametrize("title", [None, 123])
def test_select_bigchats_does_not_swallow_invalid_title_types(title):
    with pytest.raises(AttributeError):
        select_bigchats([(1, title)], date(2026, 8, 20))


def test_select_bigchats_consumes_the_iterable_once_in_order():
    visited = []

    class Worksheets:
        def __iter__(self):
            assert visited == []
            for item in [
                (9, "MEMBERS_INFO"),
                (4, "오전 빅챗 26-08-20 10:00~12:00"),
                (4, "모레 빅챗 26-08-21 19:00~21:00"),
            ]:
                visited.append(item[0])
                yield item

    matched, parsed, ignored = select_bigchats(Worksheets(), date(2026, 8, 20))
    assert visited == [9, 4, 4]
    assert matched == [
        (
            4,
            BigchatEvent(
                "오전 빅챗",
                datetime(2026, 8, 20, 10, tzinfo=KST),
                datetime(2026, 8, 20, 12, tzinfo=KST),
            ),
        )
    ]
    assert parsed == [
        "'오전 빅챗 26-08-20 10:00~12:00' -> starts 2026-08-20",
        "'모레 빅챗 26-08-21 19:00~21:00' -> starts 2026-08-21",
    ]
    assert ignored == ["MEMBERS_INFO"]


def test_select_bigchats_preserves_iterator_exception_object_and_context():
    failure = RuntimeError("시트 순회 실패")
    context = ValueError("원래 오류")
    visited = []

    def worksheets():
        visited.append(9)
        yield (9, "MEMBERS_INFO")
        try:
            raise context
        except ValueError:
            raise failure

    with pytest.raises(RuntimeError) as caught:
        select_bigchats(worksheets(), date(2026, 8, 20))
    assert caught.value is failure
    assert caught.value.__context__ is context
    assert caught.value.__cause__ is None
    assert visited == [9]


def test_reminder_result_keeps_dataclass_metadata_and_field_order():
    assert is_dataclass(ReminderResult)
    assert ReminderResult.__name__ == ReminderResult.__qualname__ == "ReminderResult"
    assert ReminderResult.__module__ == "features.bigchat.models"
    assert ReminderResult.__match_args__ == (
        "target_date",
        "bigchat_names",
        "parsed_sheet_cnt",
        "ignored_sheet_cnt",
        "applicant_cnt",
        "resolved_cnt",
        "sent_cnt",
    )
    result_fields = fields(ReminderResult)
    assert [field.name for field in result_fields] == list(
        ReminderResult.__match_args__
    )
    assert [field.type for field in result_fields] == [
        date,
        List[str],
        int,
        int,
        int,
        int,
        int,
    ]
    assert [field.default for field in result_fields] == [
        MISSING,
        MISSING,
        0,
        0,
        0,
        0,
        0,
    ]
    assert [field.default_factory for field in result_fields] == [
        MISSING,
        list,
        MISSING,
        MISSING,
        MISSING,
        MISSING,
        MISSING,
    ]
    for field in result_fields:
        assert field.init and field.repr and field.compare
        assert field.hash is None
        assert field.metadata == {}
        assert not field.kw_only
    params = ReminderResult.__dataclass_params__
    assert params.init and params.repr and params.eq
    assert not params.order and not params.unsafe_hash and not params.frozen
    assert ReminderResult.__hash__ is None


def test_reminder_result_keeps_mutable_fields_and_independent_list_defaults():
    first = ReminderResult(date(2026, 8, 20))
    second = ReminderResult(date(2026, 8, 20))
    assert first.bigchat_names == second.bigchat_names == []
    assert first.bigchat_names is not second.bigchat_names
    assert (
        first.parsed_sheet_cnt,
        first.ignored_sheet_cnt,
        first.applicant_cnt,
        first.resolved_cnt,
        first.sent_cnt,
    ) == (0, 0, 0, 0, 0)
    first.bigchat_names.append("오전 빅챗")
    assert second.bigchat_names == []
    names = ["저녁 빅챗"]
    positional = ReminderResult(date(2026, 8, 20), names, 2, 1, 4, 3, 2)
    assert positional.bigchat_names is names
    for name, value in [
        ("target_date", date(2026, 8, 21)),
        ("bigchat_names", names),
        ("parsed_sheet_cnt", 8),
        ("ignored_sheet_cnt", 7),
        ("applicant_cnt", 6),
        ("resolved_cnt", 5),
        ("sent_cnt", 4),
    ]:
        setattr(first, name, value)
        assert getattr(first, name) is value
    assert first.bigchat_names is positional.bigchat_names


def test_reminder_runtime_type_hints_resolve_application_values():
    assert get_type_hints(ReminderResult) == {
        "target_date": date,
        "bigchat_names": List[str],
        "parsed_sheet_cnt": int,
        "ignored_sheet_cnt": int,
        "applicant_cnt": int,
        "resolved_cnt": int,
        "sent_cnt": int,
    }
    assert get_type_hints(select_bigchats) == {
        "worksheets": Iterable[Tuple[int, str]],
        "target_date": date,
        "return": Tuple[List[Tuple[int, BigchatEvent]], List[str], List[str]],
    }


# 이 subprocess는 SDK를 미리 import하는 공용 setup 대신 표준 라이브러리 finder를 먼저 설치한다.
IMPORT_GUARD_SCRIPT = r"""
import importlib.abc
import importlib
import socket
import sys
import threading
from pathlib import Path

root = Path(sys.argv[1]).resolve()
# src 의 진입점/조립/통합 모듈과 외부 SDK. 정책 모듈은 features/shared 의 순수 값만 봐야 한다.
blocked = {
    'anna', 'app', 'bootstrap', 'config', 'integrations', 'runtime', 'slack_router',
    'requests', 'slack_sdk', 'slack_bolt', 'flask', 'gunicorn',
    'gspread', 'gspread_formatting', 'dotenv', 'pydantic_settings', 'google', 'googleapiclient', 'github',
}
assert not [name for name in sys.modules if name.split('.')[0] in blocked]
attempted = []

class ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in blocked:
            attempted.append(fullname)
            raise AssertionError('forbidden import: ' + fullname)

sys.meta_path.insert(0, ImportGuard())

def forbidden(*args, **kwargs):
    raise AssertionError('network, SDK initialization and scheduler threads forbidden')

socket.socket.connect = socket.socket.connect_ex = forbidden
socket.create_connection = socket.getaddrinfo = forbidden
threading.Thread.start = forbidden
sys.dont_write_bytecode = True
# 저장소 밖의 패키지 경로(site-packages 등)는 부모 프로세스에서 넘겨받는다. -I 가 PYTHONPATH 를 무시하기 때문이다.
sys.path[:0] = [str(root / 'src'), str(root)]
sys.path += sys.argv[2:]

# finder가 실제로 로딩 전에 거절하는지 확인하고 application의 시도와 구분한다.
for name in sorted(blocked):
    try:
        importlib.import_module(name)
    except AssertionError as error:
        assert str(error) == 'forbidden import: ' + name
    else:
        raise AssertionError('guard did not block ' + name)
attempted.clear()

def forbid_credentials(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
        if (root / 'src' / 'env') == path or (root / 'src' / 'env') in path.parents:
            raise AssertionError('environment or credentials read: ' + str(path))
        if path.name == '.env' or path.suffix == '.pem' or 'credential' in path.name.lower():
            raise AssertionError('environment or credentials read: ' + str(path))

sys.addaudithook(forbid_credentials)
module = importlib.import_module('features.bigchat.services.reminder_policy')
models = importlib.import_module('features.bigchat.models')
assert Path(module.__file__).resolve() == root / 'src/features/bigchat/services/reminder_policy.py'
assert models.ReminderResult.__module__ == 'features.bigchat.models'
assert module.select_bigchats.__module__ == 'features.bigchat.services.reminder_policy'
assert attempted == []
assert not [name for name in sys.modules if name.split('.')[0] in blocked]
for name, loaded in tuple(sys.modules.items()):
    if name.split('.')[0] in {'features', 'shared'}:
        assert Path(loaded.__file__).resolve().is_relative_to(root / 'src'), (name, loaded.__file__)
print('reminder policy isolated at ' + str(module.__file__))
"""


def test_application_bigchat_import_is_isolated_in_a_fresh_process():
    root = Path(__file__).resolve().parents[4]
    external_paths = [
        path
        for path in sys.path
        if path and not Path(path).resolve().is_relative_to(root)
    ]
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            IMPORT_GUARD_SCRIPT,
            str(root),
            *external_paths,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert completed.stdout == (
        f"reminder policy isolated at {root / 'src/features/bigchat/services/reminder_policy.py'}\n"
    )
