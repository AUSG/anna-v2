"""기능 루트의 역할 이름, 조립 코드의 의존성 방향과 정규식 이식성을 고정한다."""

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
FEATURES = SOURCE_ROOT / "features"
ROOT_FILES = {"__init__.py", "slack.py", "http.py", "jobs.py", "models.py", "ports.py"}
ROOT_DIRECTORIES = {"services", "presentation"}
# 실행 환경을 모르는 진입점·조립 모듈. features 와 shared 는 이들을 모른다.
ASSEMBLY_MODULES = {"anna", "app", "bootstrap", "slack_router", "config.env_config"}
# 전역 설정은 조립 코드와 어댑터만 읽는다. app 은 runtime 에서 받은 settings 만 쓴다.
SETTINGS_READERS = {"anna", "bootstrap", "runtime"}
SETTINGS_READER_PACKAGES = {"integrations"}
# 순수 모듈: 표준 라이브러리와 다른 순수 모듈만 import 한다.
PURE_PATTERNS = (
    "*/models.py",
    "*/ports.py",
    "*/services/*_policy.py",
    "*/services/commands.py",
    "*/services/conversation.py",
    "*/presentation/*.py",
)
PURE_HELPERS = (
    "shared/time.py",
    "shared/text.py",
    "shared/slack_commands.py",
    "shared/slack_models.py",
    "shared/slack_events.py",
    "shared/gateways.py",
)
EXTERNAL_VALUE_IMPORTS = {"shared.time": {"dateutil.tz"}}
# services 와 presentation 은 게이트웨이(Protocol)만 보고 어댑터나 SDK 는 모른다.
ADAPTER_PACKAGES = {
    "integrations",
    "slack_sdk",
    "slack_bolt",
    "requests",
    "flask",
    "gspread",
}
# Rust regex crate 로 옮길 수 있게 lookaround 와 backreference 를 쓰지 않는다.
LOOKAROUND_TOKENS = ("(?=", "(?!", "(?<=", "(?<!")
BACKREFERENCE = re.compile(r"\\[1-9]")


def _module_name(path, source_root):
    parts = path.relative_to(source_root).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path, source_root):
    package = path.relative_to(source_root).parent.parts
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                if node.level > len(package):
                    yield node.lineno, "__invalid_relative_import__"
                    continue
                prefix = package[: len(package) - node.level + 1]
                module = ".".join((*prefix, *module.split("."))).rstrip(".")
            for alias in node.names:
                candidate = f"{module}.{alias.name}"
                target = source_root.joinpath(*candidate.split("."))
                if (
                    alias.name == "*"
                    or target.with_suffix(".py").is_file()
                    or (target / "__init__.py").is_file()
                ):
                    yield node.lineno, candidate
                else:
                    yield node.lineno, module


def _source_files(root):
    return sorted(
        path for path in root.rglob("*.py") if "__pycache__" not in path.parts
    )


def _pure_module_paths(source_root):
    features = source_root / "features"
    paths = {path for pattern in PURE_PATTERNS for path in features.glob(pattern)}
    paths.update(
        source_root / helper
        for helper in PURE_HELPERS
        if (source_root / helper).is_file()
    )
    for path in tuple(paths):
        for parent in path.parents:
            if parent == source_root:
                break
            initializer = parent / "__init__.py"
            if initializer.is_file():
                paths.add(initializer)
    return paths


def _pure_import_violations(paths, source_root):
    allowed = {_module_name(path, source_root) for path in paths}
    violations = []
    for path in sorted(paths):
        external = EXTERNAL_VALUE_IMPORTS.get(_module_name(path, source_root), set())
        for line, name in _imports(path, source_root):
            if (
                name.split(".")[0] not in sys.stdlib_module_names
                and name not in allowed
                and name not in external
            ):
                violations.append(
                    f"{path.relative_to(source_root)}:{line} imports {name}"
                )
    return violations


def _import_violations(paths, source_root, forbidden):
    """forbidden 모듈(또는 그 하위)을 import 하는 위치."""
    violations = []
    for path in sorted(paths):
        for line, name in _imports(path, source_root):
            if any(
                name == module or name.startswith(f"{module}.") for module in forbidden
            ):
                violations.append(
                    f"{path.relative_to(source_root)}:{line} imports {name}"
                )
    return violations


def _is_re_compile(node):
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "compile":
        return isinstance(func.value, ast.Name) and func.value.id == "re"
    return False


def _pattern_sources(tree):
    """re.compile 에 넘긴 패턴 문자열. f-string 은 상수 조각과 모듈 상수로 풀어 본다."""
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        constants[target.id] = node.value.value

    def resolve(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant):
                    parts.append(str(value.value))
                elif isinstance(value, ast.FormattedValue):
                    if (
                        isinstance(value.value, ast.Name)
                        and value.value.id in constants
                    ):
                        parts.append(constants[value.value.id])
                    else:
                        parts.append(f"<unresolved:{ast.dump(value.value)}>")
            return "".join(parts)
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_re_compile(node) and node.args:
            yield node.lineno, resolve(node.args[0])


def _regex_violations(paths, source_root):
    violations = []
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for line, pattern in _pattern_sources(tree):
            location = f"{path.relative_to(source_root)}:{line}"
            if pattern is None:
                violations.append(
                    f"{location} compiles a pattern that is not a string literal"
                )
                continue
            if any(token in pattern for token in LOOKAROUND_TOKENS):
                violations.append(f"{location} uses lookaround: {pattern!r}")
            if BACKREFERENCE.search(pattern):
                violations.append(f"{location} uses a backreference: {pattern!r}")
    return violations


# --- 규칙 --------------------------------------------------------------------------


def test_feature_roots_contain_only_shared_role_names():
    violations = []
    for feature in FEATURES.iterdir():
        if not feature.is_dir() or feature.name == "__pycache__":
            continue
        for child in feature.iterdir():
            if child.name == "__pycache__":
                continue
            allowed = ROOT_DIRECTORIES if child.is_dir() else ROOT_FILES
            if child.name not in allowed:
                violations.append(str(child.relative_to(ROOT)))
    assert violations == []


def test_features_and_shared_do_not_import_assembly_modules():
    paths = _source_files(FEATURES) + _source_files(SOURCE_ROOT / "shared")
    assert _import_violations(paths, SOURCE_ROOT, ASSEMBLY_MODULES) == []


def test_only_assembly_and_adapters_read_global_settings():
    readers = {
        _module_name(path, SOURCE_ROOT)
        for path in _source_files(SOURCE_ROOT)
        for _, name in _imports(path, SOURCE_ROOT)
        if name == "config.env_config" or name.startswith("config.env_config.")
    }
    assert readers  # 조립 코드는 설정을 읽어야 한다
    unexpected = {
        module
        for module in readers
        if module not in SETTINGS_READERS
        and module.split(".")[0] not in SETTINGS_READER_PACKAGES
    }
    assert unexpected == set()


def test_pure_modules_import_only_stdlib_and_pure_modules():
    assert _pure_import_violations(_pure_module_paths(SOURCE_ROOT), SOURCE_ROOT) == []


def test_services_and_presentation_do_not_import_adapters_or_sdks():
    paths = list(FEATURES.glob("*/services/*.py")) + list(
        FEATURES.glob("*/presentation/*.py")
    )
    assert paths
    assert _import_violations(paths, SOURCE_ROOT, ADAPTER_PACKAGES) == []


def test_regexes_stay_portable_to_the_rust_regex_crate():
    assert _regex_violations(_source_files(SOURCE_ROOT), SOURCE_ROOT) == []


def test_old_layer_packages_are_not_kept_as_compatibility_shims():
    for package in ("application", "handler", "implementation", "util"):
        assert not (SOURCE_ROOT / package).exists()


# --- 검사기 자체 검증 -------------------------------------------------------------


@pytest.fixture
def pure_source(tmp_path):
    source_root = tmp_path / "src"
    for relative, contents in {
        "features/__init__.py": "",
        "features/example/__init__.py": "",
        "features/example/models.py": "",
        "features/example/ports.py": "",
        "features/example/slack.py": "",
        "shared/time.py": "from dateutil.tz import gettz\nKST = gettz('Asia/Seoul')\n",
        "shared/loading_emoji.py": "",
    }.items():
        path = source_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return source_root


@pytest.mark.parametrize(
    ("source", "allowed"),
    [
        ("from dataclasses import dataclass", True),
        ("from features.example import ports", True),
        ("from . import ports", True),
        ("from shared.time import KST", True),
        ("from features.example import slack", False),
        ("from . import slack", False),
        ("import features.example.slack", False),
        ("from features.example import *", False),
        ("from ... import bootstrap", False),
        ("from shared import loading_emoji", False),
        ("from config.env_config import Settings", False),
        ("import requests", False),
        ("from pydantic import BaseModel", False),
    ],
)
def test_pure_import_guard_checks_exact_dependencies(pure_source, source, allowed):
    (pure_source / "features/example/models.py").write_text(source, encoding="utf-8")
    violations = _pure_import_violations(_pure_module_paths(pure_source), pure_source)
    assert (violations == []) is allowed


@pytest.mark.parametrize("relative", ["shared/time.py", "features/example/__init__.py"])
def test_pure_import_guard_checks_helpers_and_package_initializers(
    pure_source, relative
):
    (pure_source / relative).write_text("import requests", encoding="utf-8")
    violations = _pure_import_violations(_pure_module_paths(pure_source), pure_source)
    assert f"{relative}:1 imports requests" in violations


@pytest.mark.parametrize(
    "relative",
    [
        "features/added/models.py",
        "features/added/ports.py",
        "features/added/services/added_policy.py",
        "features/added/services/commands.py",
        "features/added/services/conversation.py",
        "features/added/presentation/blocks.py",
    ],
)
def test_pure_import_guard_discovers_new_feature_modules(pure_source, relative):
    path = pure_source / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import requests", encoding="utf-8")
    violations = _pure_import_violations(_pure_module_paths(pure_source), pure_source)
    assert f"{relative}:1 imports requests" in violations


@pytest.mark.parametrize(
    ("source", "forbidden", "allowed"),
    [
        ("from shared.gateways import SlackGateway", ADAPTER_PACKAGES, True),
        ("from integrations.slack import SlackClient", ADAPTER_PACKAGES, False),
        ("import integrations", ADAPTER_PACKAGES, False),
        ("from slack_sdk.errors import SlackApiError", ADAPTER_PACKAGES, False),
        ("import requests", ADAPTER_PACKAGES, False),
        ("from runtime import Runtime", ASSEMBLY_MODULES, True),
        ("from app import create_app", ASSEMBLY_MODULES, False),
        ("import slack_router", ASSEMBLY_MODULES, False),
        ("from config.env_config import Settings", ASSEMBLY_MODULES, False),
        ("from config.log_config import init_logger", ASSEMBLY_MODULES, True),
    ],
)
def test_import_guard_matches_forbidden_modules_and_their_submodules(
    pure_source, source, forbidden, allowed
):
    path = pure_source / "features/example/slack.py"
    path.write_text(source, encoding="utf-8")
    violations = _import_violations([path], pure_source, forbidden)
    assert (violations == []) is allowed


@pytest.mark.parametrize(
    ("source", "allowed"),
    [
        ('import re\nP = re.compile(r"<@([A-Z0-9]+)>")', True),
        (
            'import re\nP = re.compile(r"(?:https?://|www\\.)[^\\s]+", re.IGNORECASE)',
            True,
        ),
        ('import re\nP = re.compile(r"^\\S+@\\S+\\.\\S+$")', True),
        ('import re\nP = re.compile(r"(?=x)")', False),
        ('import re\nP = re.compile(r"(?!x)")', False),
        ('import re\nP = re.compile(r"(?<=x)y")', False),
        ('import re\nP = re.compile(r"(?<!x)y")', False),
        ('import re\nP = re.compile(r"(a)\\1")', False),
        ('import re\nP = re.compile("(a)\\\\1")', False),
        (
            'import re\nU = r"[^()]+"\nP = re.compile(rf"\\[([^\\]]+)\\]\\(({U})\\)")',
            True,
        ),
        ('import re\nU = r"(?=x)"\nP = re.compile(rf"a{U}")', False),
        ('import re\nU = r"a"\nP = re.compile(rf"(?<=b){U}")', False),
        ("import re\nP = re.compile(''.join(['a']))", False),
    ],
)
def test_regex_guard_scans_literals_and_module_constants(tmp_path, source, allowed):
    path = tmp_path / "patterns.py"
    path.write_text(source, encoding="utf-8")
    violations = _regex_violations([path], tmp_path)
    assert (violations == []) is allowed
