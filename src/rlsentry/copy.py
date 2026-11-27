"""The throwaway copy: built from a project's migrations, kept apart from the machine, always destroyed.

One `Copy` owns every process, directory and port of a run; nothing else starts or stops one.
"""

from __future__ import annotations

import http.client
import json
import os
import pwd
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from importlib import resources
from pathlib import Path

from . import direct, pg, seed, statements
from .inputs import Project
from .stops import Stop, printable
from .versions import POSTGRESQL, POSTGREST, Programs, Versions, accept, parse_postgrest

SUPERUSER = "rlsentry"
MIGRATIONS_ROLE = "postgres"
DB_PORT = 5432  # names the socket file only: the server listens on no TCP port
WATCHED_ROLES = ("anon", "authenticated", "authenticator")
START_TIMEOUT = 30.0
SAFE_SEARCH_PATH = "pg_catalog, pg_temp"  # pg_temp named last, or it is searched before the catalog


def runs_root() -> Path:
    return Path(tempfile.gettempdir()) / f"rlsentry-runs-{os.getuid()}"


def _start_time(pid: int) -> str | None:
    """The process's start time (clock ticks since boot), to tell it from a later one with its pid."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    return stat.rsplit(")", 1)[1].split()[19]


def _alive(pid: int | None, start: str | None) -> bool:
    return bool(pid) and _start_time(pid) is not None and _start_time(pid) == start


def _gone(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = None
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except OSError:
            return True
        if state == "Z":
            return True
        time.sleep(0.05)
    return False


def _processes_in(directory: Path) -> list[int]:
    """Every process working in `directory`: the copy's programs start there, and their children
    (PostgreSQL's backends, each in a session of its own) inherit it."""
    found = []
    for proc in Path("/proc").iterdir():
        if proc.name.isdigit():
            try:
                cwd = os.readlink(proc / "cwd")
            except OSError:
                continue
            if cwd == str(directory) or cwd.startswith(f"{directory}/") or cwd == f"{directory} (deleted)":
                found.append(int(proc.name))
    return found


def _kill_all_in(directory: Path) -> None:
    for pid in _processes_in(directory):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    for pid in _processes_in(directory):
        _gone(pid, 10)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _service_account() -> tuple[int, int] | None:
    """When run as root, the unprivileged account the copy's programs run as; else None (the user)."""
    if os.geteuid() != 0:
        return None
    for name in ("postgres", "nobody"):
        try:
            pw = pwd.getpwnam(name)
        except KeyError:
            continue
        return pw.pw_uid, pw.pw_gid
    raise Stop("running as root, and there is neither a `postgres` nor a `nobody` account to run the copy as")


def remove_dead_runs(say) -> None:
    """Remove the copies of runs that are no longer alive (killed so they could not clean up)."""
    root = runs_root()
    if not root.is_dir():
        return
    for record in sorted(root.glob("*.json")):
        try:
            run = json.loads(record.read_text())
        except (OSError, ValueError):
            continue
        if _alive(run.get("pid"), run.get("start")):
            continue
        stopped = []
        directory = root / record.stem
        for what, sig in (("postgrest", signal.SIGKILL), ("postgres", signal.SIGQUIT)):
            proc = run.get(what)
            if proc and _alive(proc["pid"], proc["start"]):
                os.kill(proc["pid"], sig)  # SIGQUIT: PostgreSQL's immediate shutdown, backends included
                if not _gone(proc["pid"], 10):
                    os.kill(proc["pid"], signal.SIGKILL)
                    _gone(proc["pid"], 10)
                stopped.append(f"its {'REST layer' if what == 'postgrest' else 'database server'} (pid {proc['pid']})")
        _kill_all_in(directory)
        shutil.rmtree(directory, ignore_errors=True)
        record.unlink(missing_ok=True)
        say(
            f"removed the copy left by an earlier run that is no longer alive (rlsentry pid {run.get('pid')}): "
            + (", ".join(stopped) + " stopped, " if stopped else "")
            + f"{directory} deleted"
        )
    for directory in root.iterdir():
        # A run writes its record before its directory, so a directory without one is a removal cut short.
        if directory.is_dir() and not (root / f"{directory.name}.json").exists():
            shutil.rmtree(directory, ignore_errors=True)


class Copy:
    def __init__(self, project: Project, programs: Programs, versions: Versions, say=None):
        self.project = project
        self.programs = programs
        self.versions = versions
        self.say = say or (lambda msg: print(msg, file=sys.stderr))
        self.account = None
        self.dir: Path | None = None
        self.record: Path | None = None
        self.rest_port: int | None = None
        self.jwt_secret = secrets.token_urlsafe(48)  # in memory and in PostgREST's environment only
        self._procs: dict[str, subprocess.Popen] = {}
        self._run = {"pid": os.getpid(), "start": _start_time(os.getpid())}

    # -- the context manager ---------------------------------------------------------------------

    def __enter__(self) -> Copy:
        try:
            self._build()
        except BaseException:
            self._destroy()
            raise
        return self

    def __exit__(self, *exc) -> bool:
        self._destroy()
        return False

    @property
    def socket_dir(self) -> str:
        return str(self.dir / "sock")

    @property
    def rest_url(self) -> str:
        return f"http://127.0.0.1:{self.rest_port}"

    def connect(self, user: str = SUPERUSER) -> pg.Connection:
        """A connection to the copy's database. The superuser's is shielded from the settings the
        migrations put on the database they own (a role to switch to, a search_path that puts their
        own objects before the catalog, read-only transactions, ...): each one is sent back at startup
        with the server's own value, and the search_path is the catalog's alone."""
        if user != SUPERUSER:
            return pg.Connection(self.socket_dir, DB_PORT, user)
        return pg.Connection(self.socket_dir, DB_PORT, user, settings={
            **self._server_values_of_database_settings(), "search_path": SAFE_SEARCH_PATH,
        })

    def _server_values_of_database_settings(self) -> dict[str, str]:
        """For each setting made on database postgres (for every role, or for the superuser), the
        value the server gives it elsewhere, read through database template1, which no migration owns.
        Names the server does not know (placeholders such as pgrst.*) are left out: no rlsentry query
        reads them, and the settings check names those it must."""
        with pg.Connection(self.socket_dir, DB_PORT, SUPERUSER, "template1",
                           settings={"search_path": SAFE_SEARCH_PATH}) as admin:
            rows = admin.rows(
                "select n.name, pg_catalog.current_setting(n.name, true) "
                "from (select pg_catalog.split_part(pg_catalog.unnest(s.setconfig), '=', 1) as name "
                "      from pg_catalog.pg_db_role_setting s "
                "      where s.setdatabase in (0, (select d.oid from pg_catalog.pg_database d where d.datname = 'postgres')) "
                "      and s.setrole in (0, (select r.oid from pg_catalog.pg_roles r where r.rolname = current_user))) n "
                "where pg_catalog.current_setting(n.name, true) is not null"
            )
        return dict(rows)

    # -- building --------------------------------------------------------------------------------

    def _build(self) -> None:
        remove_dead_runs(self.say)
        self.account = _service_account()
        self._make_run_directory()
        self._init_database()
        self._start_database()
        with self.connect() as admin:
            server = admin.rows("show server_version")[0][0].split()[0]
            self.versions.postgres = accept(POSTGRESQL, server, "the running server")
            admin.execute(resources.files("rlsentry").joinpath("supabase_setup.sql").read_text())
        with self.connect(MIGRATIONS_ROLE) as conn:
            for path in self.project.migrations:
                self._apply(conn, path)
        self._check_settings()
        with self.connect() as admin, self.connect(MIGRATIONS_ROLE) as migrations:
            seed.fill(admin, migrations, direct.table_oids(admin, self.project.exposed_schemas),
                      direct.users_oid(admin))
        self._start_rest()  # after seeding: PostgREST reads the schema once, at start

    def _make_run_directory(self) -> None:
        root = runs_root()
        root.mkdir(mode=0o700, exist_ok=True)
        st = root.lstat()
        if not root.is_dir() or root.is_symlink() or st.st_uid != os.getuid():
            raise Stop(f"{root} is not a directory owned by this user; rlsentry will not build a copy in it")
        # The server's account (when root) must reach its own run directory, and list nothing else.
        os.chmod(root, 0o711 if self.account else 0o700)
        run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{os.getpid()}-{secrets.token_hex(4)}"
        self.record = root / f"{run_id}.json"
        self._write_record()  # the record comes first, so a directory never exists without one
        self.dir = root / run_id
        self.dir.mkdir(mode=0o700)
        (self.dir / "sock").mkdir(mode=0o700)
        if self.account:
            for d in (self.dir, self.dir / "sock"):
                os.chown(d, *self.account)

    def _write_record(self) -> None:
        tmp = self.record.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._run))
        tmp.replace(self.record)

    def _spawn(self, what: str, argv: list[str], env: dict[str, str] | None = None) -> subprocess.Popen:
        log = open(self.dir / f"{what}.log", "ab")
        if self.account:
            os.fchown(log.fileno(), *self.account)
        kwargs = {}
        if self.account:
            kwargs = {"user": self.account[0], "group": self.account[1], "extra_groups": []}
        base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "TZ": "UTC"}
        proc = subprocess.Popen(
            argv, cwd=self.dir, env={**base, **(env or {})}, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True, umask=0o077, **kwargs,
        )
        log.close()
        return proc

    def _log_tail(self, what: str) -> str:
        try:
            lines = (self.dir / f"{what}.log").read_text(errors="replace").strip().splitlines()
        except OSError:
            return ""
        return printable(" / ".join(lines[-3:]))

    def _init_database(self) -> None:
        proc = self._spawn("initdb", [
            str(self.programs.initdb), "-D", str(self.dir / "data"), "-U", SUPERUSER,
            "--auth-local=trust", "--auth-host=reject", "-E", "UTF8", "--locale=C", "--no-instructions",
        ])
        if proc.wait() != 0:
            raise Stop(f"the copy's database could not be created: {self._log_tail('initdb')}")
        # Only the socket, in a directory only this run can reach: no TCP connection is accepted.
        (self.dir / "data" / "pg_hba.conf").write_text("local all all trust\n")

    def _start_database(self) -> None:
        proc = self._spawn("postgres", [
            str(self.programs.postgres), "-D", str(self.dir / "data"), "-p", str(DB_PORT),
            "-c", "listen_addresses=", "-c", f"unix_socket_directories={self.socket_dir}",
            "-c", "unix_socket_permissions=0700", "-c", "fsync=off", "-c", "synchronous_commit=off",
            "-c", "full_page_writes=off", "-c", "max_connections=40",
        ])
        self._procs["postgres"] = proc
        self._run["postgres"] = {"pid": proc.pid, "start": _start_time(proc.pid)}
        self._write_record()
        deadline = time.monotonic() + START_TIMEOUT
        while True:
            try:
                self.connect().close()
                return
            except (OSError, pg.PgError):
                if proc.poll() is not None or time.monotonic() > deadline:
                    raise Stop(f"the copy's database server did not start: {self._log_tail('postgres')}") from None
                time.sleep(0.05)

    def _apply(self, conn: pg.Connection, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise Stop(f"migration {path.name} could not be read: {e}") from None
        conn.execute("begin")
        for line, statement in statements.split(text):
            try:
                conn.execute(statement)
            except pg.PgError as e:
                conn.execute("rollback")
                shown = statement if len(statement) <= 600 else statement[:600] + " ..."
                more = "".join(f"\n  {label}: {e.fields[k]}" for k, label in (("D", "detail"), ("H", "hint")) if k in e.fields)
                raise Stop(
                    f"migration {path.name} failed at line {line}: {e.message} "
                    f"(SQLSTATE {e.code}){more}\n  the statement: {shown}"
                ) from None
        conn.execute("commit")

    def _check_settings(self) -> None:
        """Every setting the migrations put on PostgREST's or the visitor's roles, or any pgrst.* one."""
        with self.connect() as admin:
            rows = admin.rows(
                "select coalesce(d.datname, ''), coalesce(r.rolname, ''), pg_catalog.unnest(s.setconfig) "
                "from pg_catalog.pg_db_role_setting s "
                "left join pg_catalog.pg_database d on d.oid = s.setdatabase "
                "left join pg_catalog.pg_roles r on r.oid = s.setrole order by 1, 2, 3"
            )
        found = []
        for database, role, setting in rows:
            name, _, value = setting.partition("=")
            if role in WATCHED_ROLES or name.lower().startswith("pgrst."):
                where = f"role {role}" if role else f"database {database}"
                if role and database:
                    where += f" in database {database}"
                found.append(f"{name} = {value!r} on {where}")
        if found:
            raise Stop(
                "the migrations make settings that, on Supabase, change how the REST layer or the "
                "roles a request passes through (anon, authenticated, authenticator) behave; the copy "
                "does not apply them, so its answers would not be the project's: "
                + printable("; ".join(found))
            )

    def _start_rest(self) -> None:
        for attempt in range(3):
            self.rest_port = _free_port()
            proc = self._spawn("postgrest", [str(self.programs.postgrest)], env={
                "PGRST_DB_URI": f"postgres://authenticator@/postgres?host={self.socket_dir}&port={DB_PORT}",
                "PGRST_DB_SCHEMAS": ",".join(self.project.exposed_schemas),
                "PGRST_DB_ANON_ROLE": "anon",
                "PGRST_DB_CONFIG": "false",
                "PGRST_DB_CHANNEL_ENABLED": "false",
                "PGRST_DB_EXTRA_SEARCH_PATH": "public, extensions",
                "PGRST_DB_PLAN_ENABLED": "false",
                "PGRST_DB_AGGREGATES_ENABLED": "false",
                "PGRST_DB_TX_END": "commit",
                "PGRST_SERVER_HOST": "127.0.0.1",
                "PGRST_SERVER_PORT": str(self.rest_port),
                "PGRST_JWT_SECRET": self.jwt_secret,
            })
            self._procs["postgrest"] = proc
            self._run["postgrest"] = {"pid": proc.pid, "start": _start_time(proc.pid), "port": self.rest_port}
            self._write_record()
            server = self._wait_rest(proc)
            if server is not None:
                found = parse_postgrest(server)
                if found is None:
                    raise Stop(f"the copy's REST layer did not say its version (Server: {printable(server)!r})")
                self.versions.postgrest = accept(POSTGREST, found, "the running REST layer")
                return
            self._stop("postgrest", signal.SIGTERM)  # most likely the port was taken meanwhile
        raise Stop(f"the copy's REST layer did not start: {self._log_tail('postgrest')}")

    def _wait_rest(self, proc: subprocess.Popen) -> str | None:
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline and proc.poll() is None:
            conn = http.client.HTTPConnection("127.0.0.1", self.rest_port, timeout=2)
            try:
                conn.request("GET", "/")
                response = conn.getresponse()
                response.read()
                if response.status == 200:
                    return response.getheader("Server", "")
            except OSError:
                pass
            finally:
                conn.close()
            time.sleep(0.05)
        return None

    # -- destroying ------------------------------------------------------------------------------

    def _stop(self, what: str, sig: int) -> None:
        proc = self._procs.pop(what, None)
        if proc is None:
            return
        try:
            proc.send_signal(sig)
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()

    def _destroy(self) -> None:
        """Stop every process of the copy, wait until they are gone, delete its directory."""
        handlers = {}
        if threading.current_thread() is threading.main_thread():
            handlers = {s: signal.signal(s, signal.SIG_IGN) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            self._stop("postgrest", signal.SIGTERM)
            self._stop("postgres", signal.SIGINT)  # fast shutdown: ends every session first
            if self.dir is not None:
                _kill_all_in(self.dir)  # none after a clean shutdown; a hung backend otherwise
                shutil.rmtree(self.dir, ignore_errors=True)
                if self.dir.exists():
                    shutil.rmtree(self.dir)  # say why, rather than leave it silently
                self.dir = None
            if self.record is not None:
                self.record.unlink(missing_ok=True)
                self.record = None
        finally:
            for s, h in handlers.items():
                signal.signal(s, h)
