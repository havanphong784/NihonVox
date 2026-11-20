"""Run dependency-free JavaScript behavior tests when Node is available."""
import shutil
import subprocess
from pathlib import Path

import pytest


def test_browser_controller_behaviors():
    node = shutil.which('node')
    if node is None:
        pytest.skip('Node optional: run node --test tests/test_frontend.js to test the browser controller')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, '--test', 'tests/test_frontend.js'], cwd=root,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
