"""Draait de node-unittests van de directe controle in de web-editor (overslaan zonder node)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(shutil.which("node") is None, reason="node niet beschikbaar")
def test_editor_checks_node():
    r = subprocess.run(["node", "--test", str(ROOT / "tests/web/test_editor_checks.js"), str(ROOT / "tests/web/test_verzetten.js"), str(ROOT / "tests/web/test_progress.js")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
