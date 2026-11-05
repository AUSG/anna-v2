import subprocess

import pytest

from tools.sheets_verification import runner


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    def git(*args):
        return subprocess.check_output(
            [
                "git",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "commit.gpgsign=false",
                *args,
            ],
            cwd=tmp_path,
            text=True,
        ).strip()

    git("init", "--quiet")
    for name in [
        "src/app.py",
        "tools/__init__.py",
        "tools/sheets_verification/runner.py",
        "pyproject.toml",
        "uv.lock",
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "fixture",
    )
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    return tmp_path, git("rev-parse", "HEAD")


def test_manifest_binds_application_tool_and_dependency_inputs(checkout):
    _, head = checkout
    result = runner.source_manifest(head)
    assert result["head"] == head
    assert set(result["files"]) == {
        "src/app.py",
        "tools/__init__.py",
        "tools/sheets_verification/runner.py",
        "pyproject.toml",
        "uv.lock",
    }


@pytest.mark.parametrize(
    "path", ["src/untracked.py", "tools/sheets_verification/untracked.py"]
)
def test_untracked_runtime_or_verifier_code_blocks_live_execution(checkout, path):
    root, head = checkout
    (root / path).write_text("# unreviewed\n")
    with pytest.raises(RuntimeError, match="Untracked"):
        runner.source_manifest(head)


@pytest.mark.parametrize(
    "path",
    [
        "src/app.py",
        "tools/__init__.py",
        "tools/sheets_verification/runner.py",
        "pyproject.toml",
        "uv.lock",
    ],
)
def test_modified_verified_inputs_block_live_execution(checkout, path):
    root, head = checkout
    (root / path).write_text("# modified\n")
    with pytest.raises(subprocess.CalledProcessError):
        runner.source_manifest(head)
