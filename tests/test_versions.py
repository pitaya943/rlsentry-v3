"""S-7: a PostgreSQL or PostgREST of another release series stops the run; within it, the exact
versions the copy ran are named. The stand-in programs here are the one stand-in S-10 allows."""

import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import assert_no_copy_left, records, rlsentry, write
from rlsentry.versions import find

REAL_POSTGRES = find("postgres")
REAL_POSTGREST = find("postgrest")


def stand_in(folder: Path, name: str, version_line: str, real: Path | None = None) -> None:
    """A program that reports `version_line` for --version; with `real`, it is that program otherwise."""
    script = folder / name
    rest = f'exec "{real}" "$@"' if real else "exit 1"
    script.write_text(
        f'#!/bin/sh\nif [ "$1" = "--version" ]; then echo "{version_line}"; exit 0; fi\n{rest}\n'
    )
    script.chmod(0o755)


@pytest.fixture
def project(tmp_path):
    return write(tmp_path / "project", {"001_t.sql": "create table t (id int primary key);"})


def run_with(public_dir, project, **programs):
    for name, line in programs.items():
        stand_in(public_dir, name, line)
    before = records()
    done = rlsentry(project, env={"PATH": f"{public_dir}:{os.environ['PATH']}"})
    assert records() == before, "a copy was started"
    assert_no_copy_left()
    return done


@pytest.mark.parametrize("line, found", [
    ("postgres (PostgreSQL) 16.14 (Ubuntu 16.14-1)", "16.14"),
    ("postgres (PostgreSQL) 17.2", "17.2"),
    ("postgres (PostgreSQL) 15.8", "15.8"),
])
def test_postgresql_outside_the_series_stops_before_anything_is_built(public_dir, project, line, found):
    done = run_with(public_dir, project, postgres=line)
    assert done.returncode == 2
    assert f"PostgreSQL {found} found" in done.stderr
    assert "needs PostgreSQL 16 at 16.15 or later" in done.stderr
    assert "copy built" not in done.stdout


@pytest.mark.parametrize("line, found", [
    ("PostgREST 12.2.11", "12.2.11"),
    ("PostgREST 12.1.3", "12.1.3"),
    ("PostgREST 13.0.0", "13.0.0"),
])
def test_postgrest_outside_the_series_stops_before_anything_is_built(public_dir, project, line, found):
    done = run_with(public_dir, project, postgrest=line)
    assert done.returncode == 2
    assert f"PostgREST {found} found" in done.stderr
    assert "needs PostgREST 12.2 at 12.2.12 or later" in done.stderr
    assert "copy built" not in done.stdout


def test_a_missing_program_stops_naming_it(project):
    done = rlsentry(project, env={"PATH": "/usr/bin:/bin"})  # PostgREST lives elsewhere
    assert REAL_POSTGREST.parent not in (Path("/usr/bin"), Path("/bin"))
    assert done.returncode == 2
    assert "`postgrest` was not found" in done.stderr
    assert_no_copy_left()


def real_version(program: Path, pattern: str) -> str:
    out = subprocess.run([program, "--version"], capture_output=True, text=True).stdout
    return re.search(pattern, out).group(1)


def test_within_the_series_the_run_names_the_exact_versions(project):
    done = rlsentry(project)
    assert done.returncode == 0, done.stderr
    pg = real_version(REAL_POSTGRES, r"\(PostgreSQL\) (\S+)")
    rest = real_version(REAL_POSTGREST, r"PostgREST (\S+)")
    assert f"PostgreSQL {pg} and PostgREST {rest}" in done.stdout


def test_the_running_servers_version_decides(public_dir, project):
    # Both programs claim another version within the series; the copy really runs the installed ones.
    stand_in(public_dir, "postgres", "postgres (PostgreSQL) 16.99", REAL_POSTGRES)
    stand_in(public_dir, "postgrest", "PostgREST 12.2.99", REAL_POSTGREST)
    done = rlsentry(project, env={"PATH": f"{public_dir}:{os.environ['PATH']}"})
    assert done.returncode == 0, done.stderr
    pg = real_version(REAL_POSTGRES, r"\(PostgreSQL\) (\S+)")
    rest = real_version(REAL_POSTGREST, r"PostgREST (\S+)")
    assert f"PostgreSQL {pg} and PostgREST {rest}" in done.stdout
    assert "16.99" not in done.stdout and "12.2.99" not in done.stdout
    assert_no_copy_left()
