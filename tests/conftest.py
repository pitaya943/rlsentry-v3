"""Every test here builds a real copy: PostgreSQL and PostgREST must be installed, or the suite fails."""

from __future__ import annotations

import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from rlsentry.copy import runs_root
from rlsentry.versions import find


def pytest_sessionstart(session):
    missing = [name for name in ("postgres", "initdb", "postgrest") if find(name) is None]
    if missing:
        pytest.exit(
            "rlsentry's tests need PostgreSQL 16 and PostgREST 12.2 installed; not found on the path: "
            + ", ".join(missing),
            returncode=1,
        )


@pytest.fixture
def public_dir():
    """A directory the copy's server account can reach, unlike pytest's own (mode 0700) temp dirs.

    Tests that watch a file put it here, so that only the database's own privilege checks stand
    between a migration and the file."""
    d = Path(tempfile.mkdtemp(prefix="rlsentry-test-", dir="/tmp"))
    d.chmod(0o777)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def write(folder: Path, files: dict[str, str]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text)
    return folder


def rlsentry(*args: str, env: dict | None = None, timeout: float = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "rlsentry", *map(str, args)],
        capture_output=True, text=True, timeout=timeout, env={**os.environ, **(env or {})},
    )


def start_rlsentry(*args: str) -> subprocess.Popen:
    """A run in its own process group, as a terminal's foreground job would be."""
    return subprocess.Popen(
        [sys.executable, "-m", "rlsentry", *map(str, args)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )


def wait_for_server(before: set[str], timeout: float = 60) -> tuple[Path, dict]:
    """The record of a new run once its database server has started."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for record in runs_root().glob("*.json") if runs_root().is_dir() else []:
            if record.name in before:
                continue
            try:
                run = json.loads(record.read_text())
            except ValueError:
                continue
            if "postgres" in run and (runs_root() / record.stem / "sock").exists():
                if any((runs_root() / record.stem / "sock").glob(".s.PGSQL.*")):
                    return record, run
        time.sleep(0.05)
    raise AssertionError("no run started its database server")


def records() -> set[str]:
    return {p.name for p in runs_root().glob("*.json")} if runs_root().is_dir() else set()


def pid_alive(pid: int) -> bool:
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except OSError:
        return False
    return state != "Z"


def processes_in_runs() -> list[str]:
    """Every process whose working directory is (or was) inside a run directory."""
    root = str(runs_root())
    found = []
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit():
            try:
                cwd = os.readlink(proc / "cwd")
            except OSError:
                continue
            if cwd.startswith(root):
                found.append(f"{proc.name} {cwd}")
    return found


def assert_no_copy_left() -> None:
    left = list(runs_root().iterdir()) if runs_root().is_dir() else []
    assert left == [], f"left in {runs_root()}: {left}"
    assert processes_in_runs() == []


def outcomes(stdout: str) -> dict[str, dict]:
    """The run's outcomes as printed, in order: table -> verdict (None for no verdict), the rest of
    its line (basis or reason) and, when exposed, the evidence row."""
    out: dict[str, dict] = {}
    last = None
    for line in stdout.splitlines():
        m = re.match(r"read (\S+): (exposed|no verdict); (?:basis: )?(.*)$", line)
        if m:
            last = out[m[1]] = {"verdict": "exposed" if m[2] == "exposed" else None, "text": m[3]}
        elif line.startswith("  evidence: ") and last is not None:
            last["evidence"] = json.loads(line[len("  evidence: "):])
    return out


def run(tmp_path, files: dict[str, str], name: str = "p") -> tuple[subprocess.CompletedProcess, dict]:
    done = rlsentry(write(tmp_path / name, files))
    assert_no_copy_left()
    return done, outcomes(done.stdout)
