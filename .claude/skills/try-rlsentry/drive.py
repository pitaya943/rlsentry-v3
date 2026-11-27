"""Run rlsentry once as a user would, print the transcript, and check how it ended.

    python3 drive.py EXPECTED_EXIT [rlsentry arguments ...]

Exits non-zero when rlsentry's exit code is not EXPECTED_EXIT, or when anything of the run (its
directory, a postgres or postgrest process working in it) is left after rlsentry exits."""

import os
import subprocess
import sys
from pathlib import Path

from rlsentry.copy import runs_root


def left_behind(before: set[str]) -> list[str]:
    root = runs_root()
    found = [str(p) for p in root.iterdir() if p.name not in before] if root.is_dir() else []
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit():
            try:
                cwd = os.readlink(proc / "cwd")
            except OSError:
                continue
            if cwd.startswith(str(root)):
                found.append(f"process {proc.name} in {cwd}")
    return found


def main() -> int:
    expected, args = int(sys.argv[1]), sys.argv[2:]
    root = runs_root()
    before = {p.name for p in root.iterdir()} if root.is_dir() else set()
    print(f"$ rlsentry {' '.join(args)}")
    done = subprocess.run([sys.executable, "-m", "rlsentry", *args], capture_output=True, text=True, timeout=600)
    print(done.stdout, end="")
    print(done.stderr, end="", file=sys.stderr)
    print(f"[exit {done.returncode}]")
    ok = True
    if done.returncode != expected:
        print(f"FAIL: expected exit {expected}, got {done.returncode}")
        ok = False
    left = left_behind(before)
    if left:
        print("FAIL: left after the run: " + "; ".join(left))
        ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
