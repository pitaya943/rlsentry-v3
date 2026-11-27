"""S-10: on a machine without PostgreSQL or PostgREST the suite fails, naming what is missing."""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def test_the_suite_fails_not_skips_without_postgrest():
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HERE / "test_inputs.py")],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"}, cwd=HERE.parent, timeout=300,
    )
    assert done.returncode != 0
    assert "not found on the path: postgrest" in done.stdout + done.stderr
    assert "skipped" not in done.stdout


def test_the_suite_fails_without_postgresql(tmp_path):
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HERE / "test_inputs.py")],
        capture_output=True, text=True, env={"PATH": str(tmp_path)}, cwd=HERE.parent, timeout=300,
    )
    assert done.returncode != 0
    assert "not found on the path: postgres, initdb, postgrest" in done.stdout + done.stderr
