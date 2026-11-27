"""The PostgreSQL and PostgREST release series the copy accepts, and where those programs are."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .stops import Stop

# (program shown to the user, accepted major series, lowest accepted version within it)
POSTGRESQL = ("PostgreSQL", (16,), (16, 15))
POSTGREST = ("PostgREST", (12, 2), (12, 2, 12))


@dataclass
class Versions:
    postgres: str
    postgrest: str


@dataclass
class Programs:
    postgres: Path
    initdb: Path
    postgrest: Path


def find(name: str, env_path: str | None = None) -> Path | None:
    """`name` on the path first; for PostgreSQL's programs, else the bin directory pg_config names."""
    found = shutil.which(name, path=env_path)
    if found:
        return Path(found)
    if name in ("postgres", "initdb"):
        pg_config = shutil.which("pg_config", path=env_path)
        if pg_config:
            try:
                bindir = subprocess.run(
                    [pg_config, "--bindir"], capture_output=True, text=True, timeout=10
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                bindir = ""
            if bindir and (Path(bindir) / name).is_file():
                return Path(bindir) / name
    return None


def needed(series: tuple) -> str:
    name, major, lowest = series
    return f"{name} {'.'.join(map(str, major))} at {'.'.join(map(str, lowest))} or later"


def accept(series: tuple, found: str, where: str) -> str:
    """Return the exact version if it is in the series, else stop naming program, found and needed."""
    name, major, lowest = series
    numbers = tuple(int(n) for n in found.split("."))
    if numbers[: len(major)] != major or numbers < lowest:
        raise Stop(f"{name} {found} found ({where}); rlsentry needs {needed(series)}")
    return found


def _version_output(program: Path) -> str:
    try:
        done = subprocess.run(
            [str(program), "--version"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError) as e:
        return f"<could not run: {e}>"
    return (done.stdout + done.stderr).strip()


def parse_postgres(text: str) -> str | None:
    m = re.search(r"\(PostgreSQL\) (\d+\.\d+)", text) or re.match(r"(\d+\.\d+)", text)
    return m.group(1) if m else None


def parse_postgrest(text: str) -> str | None:
    m = re.search(r"(?i)postgrest[ /](\d+\.\d+\.\d+)", text)
    return m.group(1) if m else None


def check(env_path: str | None = None) -> tuple[Programs, Versions]:
    """Find both programs and check their `--version` against the series, before anything is built."""
    if env_path is None:
        env_path = os.environ.get("PATH", "")
    paths = {}
    for name, label in (("postgres", "PostgreSQL"), ("initdb", "PostgreSQL"), ("postgrest", "PostgREST")):
        p = find(name, env_path)
        if p is None:
            raise Stop(f"{label}'s program `{name}` was not found on the path; rlsentry needs "
                       f"{needed(POSTGRESQL if label == 'PostgreSQL' else POSTGREST)}")
        paths[name] = p
    found = {}
    for name, series, parse in (
        ("postgres", POSTGRESQL, parse_postgres),
        ("postgrest", POSTGREST, parse_postgrest),
    ):
        text = _version_output(paths[name])
        version = parse(text)
        if version is None:
            raise Stop(f"{series[0]}'s `{paths[name]} --version` gave no version ({text[:200]!r}); "
                       f"rlsentry needs {needed(series)}")
        found[name] = accept(series, version, f"`{paths[name]} --version`")
    return Programs(**paths), Versions(**found)
