import socket
import subprocess
import sys

import pytest

from tools.sheets_verification.runner import ROOT


def test_tool_suite_blocks_network_without_app_conftest():
    with pytest.raises(AssertionError, match="must not contact external services"):
        socket.create_connection(("127.0.0.1", 443))


def test_module_entry_point_explains_opt_in_inputs_without_credentials():
    result = subprocess.run(
        [sys.executable, "-m", "tools.sheets_verification", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    for option in [
        "--spreadsheet-id",
        "--source-sheet-id",
        "--expected-head",
        "--credentials",
        "--run",
    ]:
        assert option in result.stdout
