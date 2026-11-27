"""S-5: the copy is gone when a run ends (finished, stopped with 2, Ctrl-C while running), and a
copy left by a killed run is removed by the next."""

import os
import signal
import socket
from pathlib import Path

import pytest

from conftest import (assert_no_copy_left, pid_alive, records, rlsentry, start_rlsentry,
                      wait_for_server, write)
from rlsentry import inputs, versions
from rlsentry.copy import Copy, runs_root
from rlsentry.stops import Stop


def descendants(root: int) -> list[int]:
    """The process and every process under it (PostgreSQL's backends each start a session of their own)."""
    children: dict[int, list[int]] = {}
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit():
            try:
                fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            except OSError:
                continue
            children.setdefault(int(fields[1]), []).append(int(proc.name))
    out, todo = [], [root]
    while todo:
        pid = todo.pop()
        out.append(pid)
        todo.extend(children.get(pid, []))
    return out


def port_open(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.mark.parametrize("ending", ["finished", "stopped", "interrupted"])
def test_the_copy_is_gone_however_the_copy_ends(tmp_path, ending):
    project = inputs.resolve(str(write(tmp_path / "p", {"001.sql": "create table t (id int);"})))
    programs, found = versions.check()
    seen = {}
    with pytest.raises((Stop, KeyboardInterrupt)) if ending != "finished" else _nothing():
        with Copy(project, programs, found) as copy:
            seen["dir"] = copy.dir
            seen["port"] = copy.rest_port
            seen["pids"] = [pid for p in copy._procs.values() for pid in descendants(p.pid)]
            assert seen["dir"].is_dir() and port_open(seen["port"])
            assert len(seen["pids"]) >= 3, "the server, its backends and the REST layer"
            assert all(pid_alive(p) for p in seen["pids"])
            if ending == "stopped":
                raise Stop("a stop while the copy runs")
            if ending == "interrupted":
                raise KeyboardInterrupt
    assert not any(pid_alive(p) for p in seen["pids"])
    assert not seen["dir"].exists()
    assert not port_open(seen["port"])
    with socket.socket() as s:
        s.bind(("127.0.0.1", seen["port"]))  # free again
    assert_no_copy_left()


class _nothing:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_finished_run_and_a_stopped_run_leave_nothing(tmp_path):
    done = rlsentry(write(tmp_path / "ok", {"001.sql": "create table t (id int);"}))
    assert done.returncode == 0
    assert_no_copy_left()
    done = rlsentry(write(tmp_path / "bad", {"001.sql": "create table t (id int);", "002.sql": "nonsense;"}))
    assert done.returncode == 2
    assert_no_copy_left()


SLOW = {"001.sql": "create table t (id int);", "002_slow.sql": "select pg_sleep(60);"}


def test_ctrl_c_while_running_destroys_the_copy(tmp_path):
    before = records()
    run = start_rlsentry(write(tmp_path / "p", SLOW))
    record, info = wait_for_server(before)
    server = info["postgres"]["pid"]
    assert pid_alive(server)
    os.killpg(run.pid, signal.SIGINT)  # what Ctrl-C sends to the terminal's foreground job
    out, err = run.communicate(timeout=60)
    assert run.returncode == 130, err
    assert "interrupted" in err
    assert not pid_alive(server)
    assert not (runs_root() / record.stem).exists() and not record.exists()
    assert_no_copy_left()


def test_sigterm_while_running_destroys_the_copy(tmp_path):
    before = records()
    run = start_rlsentry(write(tmp_path / "p", SLOW))
    record, info = wait_for_server(before)
    run.terminate()
    run.communicate(timeout=60)
    assert not pid_alive(info["postgres"]["pid"])
    assert_no_copy_left()


def test_a_copy_left_by_a_killed_run_is_removed_by_the_next(tmp_path):
    before = records()
    run = start_rlsentry(write(tmp_path / "killed", SLOW))
    record, info = wait_for_server(before)
    server = info["postgres"]["pid"]
    run.kill()
    run.communicate(timeout=60)
    left = runs_root() / record.stem
    assert pid_alive(server) and left.is_dir(), "a kill cannot be caught: the copy is still there"

    done = rlsentry(write(tmp_path / "next", {"001.sql": "create table t (id int);"}))
    assert done.returncode == 0, done.stderr
    assert "removed the copy left by an earlier run that is no longer alive" in done.stderr
    assert f"database server (pid {server}) stopped" in done.stderr
    assert f"{left} deleted" in done.stderr
    assert not pid_alive(server)
    assert_no_copy_left()
