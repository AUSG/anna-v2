"""기능 루트의 역할 이름과 조립 코드의 의존성 방향을 고정한다."""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
FEATURES = SOURCE_ROOT / "features"
ROOT_FILES = {"__init__.py", "slack.py", "http.py", "jobs.py", "models.py", "ports.py"}
ROOT_DIRECTORIES = {"services", "presentation"}
PURE_PATTERNS = (
    "*/models.py",
    "*/ports.py",
    "*/services/*_policy.py",
    "*/services/commands.py",
    "*/presentation/*.py",
)
PURE_HELPERS = (
    "features/questions/services/conversation.py",
    "shared/time.py",
    "shared/text.py",
    "shared/slack_commands.py",
)
EXTERNAL_VALUE_IMPORTS = {
    "features.members.models": {"pydantic"},
    "shared.time": {"dateutil.tz"},
}


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


def test_features_do_not_import_runtime_or_dependency_assembly():
    violations = []
    for path in FEATURES.rglob("*.py"):
        for line, name in _imports(path, SOURCE_ROOT):
            if name.split(".")[0] in {"anna", "app", "bootstrap"}:
                violations.append(f"{path.relative_to(ROOT)}:{line}: {name}")
    assert violations == []


def test_old_layer_packages_are_not_kept_as_compatibility_shims():
    for package in ("application", "handler", "implementation", "util"):
        assert not (SOURCE_ROOT / package).exists()


def test_models_ports_and_policies_do_not_import_adapters_or_settings():
    paths = {
        path
        for path in _pure_module_paths(SOURCE_ROOT)
        if "presentation" not in path.relative_to(SOURCE_ROOT).parts
    }
    assert _pure_import_violations(paths, SOURCE_ROOT) == []


def test_presentation_does_not_import_settings_or_external_clients():
    assert _pure_import_violations(_pure_module_paths(SOURCE_ROOT), SOURCE_ROOT) == []


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
        "shared/slack_middleware.py": "",
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
        ("from shared import slack_middleware", False),
        ("from config.env_config import envs", False),
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
        "features/added/presentation/blocks.py",
    ],
)
def test_pure_import_guard_discovers_new_feature_modules(pure_source, relative):
    path = pure_source / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("import requests", encoding="utf-8")
    violations = _pure_import_violations(_pure_module_paths(pure_source), pure_source)
    assert f"{relative}:1 imports requests" in violations
