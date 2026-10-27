"""main 코드를 재해석하지 않고 옮겼는지 검사한다.

기준 커밋의 모듈별 import 목록과 import를 제외한 원문 해시를 fixture에 고정한다.
경로 변경만 허용하며, 클래스·함수·조건·문구·주석의 재작성도 탐지한다.
Git 이력이나 로컬 main 브랜치 없이 CI에서도 실행할 수 있다.
"""

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
BASELINE = json.loads(
    (ROOT / "test/fixtures/main_relocation.json").read_text(encoding="utf-8")
)
MODULES = BASELINE["modules"]


def without_imports(source):
    excluded = {
        line
        for node in ast.parse(source).body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for line in range(node.lineno, node.end_lineno + 1)
    }
    return (
        "\n".join(
            line
            for number, line in enumerate(source.splitlines(), 1)
            if number not in excluded
        ).strip()
        + "\n"
    )


@pytest.mark.parametrize("module", MODULES, ids=lambda item: item["relocated"])
def test_relocated_module_keeps_main_source_except_imports(module):
    source = (ROOT / module["relocated"]).read_text(encoding="utf-8")
    digest = hashlib.sha256(without_imports(source).encode()).hexdigest()
    assert digest == module["body_sha256"], (
        f"{module['relocated']} differs from {module['original']} at "
        f"{BASELINE['baseline_commit']}; this relocation must not rewrite logic"
    )
    imports = [
        ast.dump(node)
        for node in ast.parse(source).body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert imports == module["imports"]


def test_every_production_module_is_a_relocated_main_module():
    actual = {
        str(path.relative_to(ROOT))
        for path in SOURCE_ROOT.rglob("*.py")
        if path.name != "__init__.py"
    }
    assert actual == {module["relocated"] for module in MODULES}
    for initializer in SOURCE_ROOT.rglob("__init__.py"):
        assert initializer.read_text(encoding="utf-8") == ""


def test_old_layer_packages_are_not_kept_as_compatibility_shims():
    for package in ("application", "handler", "implementation", "util"):
        assert not (SOURCE_ROOT / package).exists()


def test_source_guard_ignores_only_import_statements():
    original = '"""설명."""\nimport old\n\n# 조건을 보존한다\ndef run():\n    return False\n'
    moved = original.replace("import old", "from new import module")
    assert without_imports(original) == without_imports(moved)
    assert without_imports(original) != without_imports(moved.replace("False", "True"))
    assert without_imports(original) != without_imports(moved.replace("조건", "판단"))
