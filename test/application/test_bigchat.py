import ast
import sys
from pathlib import Path

import pytest

from application.bigchat import CreateBigchatCommand, InvalidBigchatName

SHEET_NAME = "AI 밋업 26-08-20 19:00~21:00"
APPLICATION_DIR = Path(__file__).resolve().parents[2] / "src" / "application"
# 업무 계층은 SDK·설정·어댑터를 모른다. 표준 라이브러리와 아래 패키지만 참조할 수 있다.
ALLOWED_PACKAGES = {"application", "util"}


@pytest.mark.parametrize("sheet_name", [SHEET_NAME, f"  {SHEET_NAME}  "])
def test_valid_command_keeps_the_original_title(sheet_name):
    assert CreateBigchatCommand(sheet_name).sheet_name == sheet_name


def test_invalid_command_raises_domain_error():
    with pytest.raises(InvalidBigchatName):
        CreateBigchatCommand("빅챗 23-07-31")


def test_application_layer_imports_only_allowed_packages():
    violations = []
    for path in APPLICATION_DIR.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                root = name.split(".")[0]
                if root in sys.stdlib_module_names or root in ALLOWED_PACKAGES:
                    continue
                violations.append(f"{path.name}:{node.lineno} imports {name}")
    assert violations == []
