"""S-5: the copy is gone when a run ends (finished, stopped with 2, Ctrl-C or SIGTERM while it
builds, seeds or attacks, which exit 2), and a copy left by a killed run is removed by the next."""

import os
import signal
import socket
import time
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
    assert done.returncode == 1
    assert_no_copy_left()
    done = rlsentry(write(tmp_path / "bad", {"001.sql": "create table t (id int);", "002.sql": "nonsense;"}))
    assert done.returncode == 2
    assert_no_copy_left()


SLOW = {"001.sql": "create table t (id int);", "002_slow.sql": "select pg_sleep(60);"}

# A run held in each part of its life: a migration that sleeps (build), a trigger that sleeps on the
# fake rows (seeding), a policy that sleeps on the visitor's read (attack, under the 30 s timeout).
HELD = {
    "build": (SLOW, "postgres postgres"),
    "seeding": ({"001.sql": (
        "create table t (id int);\n"
        "create function slow() returns trigger language plpgsql as "
        "$$ begin perform pg_sleep(60); return new; end $$;\n"
        "create trigger slow before insert on t for each row execute function slow();"
    )}, "INSERT"),
    "attack": ({"001.sql": (
        "create table t (id int);\n"
        "alter table t enable row level security;\n"
        "create policy slow on t for select using ((select pg_sleep(25)) is not null);"
    )}, "authenticator"),
}


def wait_for_part(record: Path, title: str, timeout: float = 60) -> None:
    """Until a backend of the run has shown `title` in its process title for a second: the run is
    held in that part (a passing query, such as PostgREST's schema load, does not count)."""
    root = runs_root() / record.stem
    deadline = time.monotonic() + timeout
    since: dict[str, float] = {}
    while time.monotonic() < deadline:
        now, showing = time.monotonic(), set()
        for proc in Path("/proc").iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if not os.readlink(proc / "cwd").startswith(str(root)):
                    continue
                line = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
            except OSError:
                continue
            if line.startswith("postgres: ") and title in line and "idle" not in line:
                showing.add(proc.name)
        since = {pid: since.get(pid, now) for pid in showing}
        if any(now - t >= 1 for t in since.values()):
            return
        time.sleep(0.05)
    raise AssertionError(f"the run never showed {title!r}")


def interrupted(tmp_path, part: str, send) -> None:
    files, title = HELD[part]
    before = records()
    run = start_rlsentry(write(tmp_path / "p", files))
    record, info = wait_for_server(before)
    server = info["postgres"]["pid"]
    wait_for_part(record, title)
    send(run)
    out, err = run.communicate(timeout=60)
    assert run.returncode == 2, err  # docs/spec/verdicts.md, exit codes: could not finish (interrupted)
    assert "interrupted: the copy was destroyed" in err
    assert not pid_alive(server)
    assert not (runs_root() / record.stem).exists() and not record.exists()
    assert_no_copy_left()


@pytest.mark.parametrize("part", HELD)
def test_ctrl_c_while_running_destroys_the_copy(tmp_path, part):
    # what Ctrl-C sends to the terminal's foreground job
    interrupted(tmp_path, part, lambda run: os.killpg(run.pid, signal.SIGINT))


@pytest.mark.parametrize("part", HELD)
def test_sigterm_while_running_destroys_the_copy(tmp_path, part):
    interrupted(tmp_path, part, lambda run: run.terminate())


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
    assert done.returncode == 1, done.stderr
    assert "removed the copy left by an earlier run that is no longer alive" in done.stderr
    assert f"database server (pid {server}) stopped" in done.stderr
    assert f"{left} deleted" in done.stderr
    assert not pid_alive(server)
    assert_no_copy_left()


@pytest.mark.parametrize("setting", [
    "alter database postgres set role = anon",
    "alter database postgres set default_transaction_read_only = on",
])
def test_the_copys_own_connection_reads_as_its_superuser_whatever_the_database_settings(tmp_path, setting):
    # The direct view (and T-02's reads of the rows the copy really holds) go through this
    # connection; a migration owns the database, so its settings must not reach it (verdict D-2, #25).
    project = inputs.resolve(str(write(tmp_path / "p", {"001.sql": (
        "create table secrets (id int primary key);\n"
        "insert into secrets values (1), (2);\n"
        "alter table secrets enable row level security;\n"
        "revoke all on secrets from anon;\n"
        + setting + ";"
    )})))
    programs, found = versions.check()
    with Copy(project, programs, found) as copy:
        with copy.connect() as admin:
            assert admin.rows("select current_user, pg_catalog.current_setting('transaction_read_only')") == [("rlsentry", "off")]
            assert admin.rows("select count(*) from public.secrets") == [("2",)]
    assert_no_copy_left()
