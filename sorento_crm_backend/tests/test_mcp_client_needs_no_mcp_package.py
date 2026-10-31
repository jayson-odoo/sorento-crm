"""The MCP HTTP client must import where the `mcp` package is not installed.

CI's backend job has no `mcp` package, and backend tests import `sorento_crm_mcp.http_client`
(`http_error_body`). A top-level `from mcp... import` anywhere on that import path breaks them there
while the local venv, which has `mcp`, hides it. A subprocess blocks `mcp` and imports from THIS checkout
(the venv's editable install points at another one).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CHECKOUT = Path(__file__).resolve().parents[2]
MCP_DIR = CHECKOUT / "sorento_crm_mcp"

SCRIPT = """
import sys
sys.modules["mcp"] = None
sys.path.insert(0, {mcp_dir!r})
from sorento_crm_mcp.http_client import http_error_body
import sorento_crm_mcp.http_client as module
print(module.__file__)
"""


def test_the_http_client_imports_with_the_mcp_package_blocked():
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT.format(mcp_dir=str(MCP_DIR))],
        capture_output=True, text=True, timeout=60,
    )
    assert done.returncode == 0, done.stderr
    printed = Path(done.stdout.strip().splitlines()[-1]).resolve()
    assert str(printed).startswith(str(MCP_DIR)), f"imported from {printed}, not from this checkout"
