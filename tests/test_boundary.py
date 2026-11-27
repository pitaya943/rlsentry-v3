"""S-5: a migration cannot reach the machine. Each attempt aims at a path the test watches, in a
directory the copy's server account can reach, so only the database's own checks stand in the way."""

import errno
import os
import threading
import time

import pytest

from conftest import assert_no_copy_left, rlsentry, write


class ReadWatch:
    """A FIFO: anyone opening it to read blocks there, and the watcher sees a reader appear."""

    def __init__(self, path):
        self.path = path
        os.mkfifo(path, 0o666)
        os.chmod(path, 0o666)
        self.read = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def _watch(self):
        while not self._stop.is_set():
            try:
                fd = os.open(self.path, os.O_WRONLY | os.O_NONBLOCK)
            except OSError as e:
                if e.errno != errno.ENXIO:  # ENXIO: no reader
                    raise
            else:
                self.read = True
                os.write(fd, b"rlsentry-test-secret\n")
                os.close(fd)  # let the reader go
            time.sleep(0.01)

    def close(self):
        self._stop.set()
        self._thread.join()


def refused(tmp_path, sql, *, statement):
    folder = write(tmp_path / "p", {"001_ok.sql": "create table a (id int);", "002_attempt.sql": sql})
    done = rlsentry(folder)
    assert done.returncode == 2, done.stdout + done.stderr
    assert "migration 002_attempt.sql failed" in done.stderr
    assert statement in done.stderr
    assert "copy built" not in done.stdout
    assert_no_copy_left()
    return done


@pytest.mark.parametrize("sql", [
    "copy (select 1) to program 'touch {target}'",
    "create table x (t text);\ncopy x from program 'touch {target}'",
])
def test_a_migration_cannot_run_a_program(tmp_path, public_dir, sql):
    target = public_dir / "ran"
    sql = sql.format(target=target)
    done = refused(tmp_path, sql, statement=sql.splitlines()[-1])
    assert "pg_execute_server_program" in done.stderr
    assert not target.exists()


@pytest.mark.parametrize("sql", [
    "create table x (t text);\ncopy x from '{target}'",
    "select pg_read_file('{target}')",
    "select pg_read_binary_file('{target}')",
    "select lo_import('{target}')",
])
def test_a_migration_cannot_read_a_file(tmp_path, public_dir, sql):
    watch = ReadWatch(public_dir / "secret")
    try:
        sql = sql.format(target=watch.path)
        done = refused(tmp_path, sql, statement=sql.splitlines()[-1])
    finally:
        watch.close()
    assert not watch.read, "the watched file was opened for reading"
    assert "rlsentry-test-secret" not in done.stdout + done.stderr


@pytest.mark.parametrize("sql", [
    "copy (select 'planted') to '{target}'",
    "select lo_export(lo_from_bytea(0, 'planted'), '{target}')",
])
def test_a_migration_cannot_write_a_file(tmp_path, public_dir, sql):
    target = public_dir / "written"
    sql = sql.format(target=target)
    refused(tmp_path, sql, statement=sql)
    assert not target.exists()


def test_a_psql_command_in_a_migration_is_not_run(tmp_path, public_dir):
    # On Supabase a migration is SQL sent to the server; a psql backslash command is no SQL at all.
    target = public_dir / "ran"
    refused(tmp_path, f"\\! touch {target}", statement=f"\\! touch {target}")
    assert not target.exists()


@pytest.mark.parametrize("extension, why", [
    ("lo", 'extension "lo" is not on the list the copy allows'),  # trusted, so only the guard refuses it
    ("unaccent", 'extension "unaccent" is not on the list the copy allows'),
    ("dblink", "permission denied to create extension"),  # opens connections; needs a superuser
    ("file_fdw", "permission denied to create extension"),  # reads files
])
def test_an_extension_outside_the_list_is_refused(tmp_path, extension, why):
    done = refused(tmp_path, f"create extension {extension}", statement=f"create extension {extension}")
    assert why in done.stderr


@pytest.mark.parametrize("sql", [
    "drop event trigger rlsentry_only_listed_extensions",
    "alter event trigger rlsentry_only_listed_extensions disable",
    "create or replace function rlsentry.only_listed_extensions() returns event_trigger language plpgsql as $$ begin end $$",
    "grant pg_execute_server_program to postgres",
    "alter role postgres superuser",
    "create language plperlu",
])
def test_the_migrations_role_cannot_lift_the_guard(tmp_path, sql):
    refused(tmp_path, sql, statement=sql)


def test_listed_extensions_are_there_for_migrations_written_for_supabase(tmp_path):
    folder = write(tmp_path / "p", {"001.sql": (
        'create extension if not exists "uuid-ossp" with schema extensions;\n'
        "create extension if not exists pgcrypto;\n"
        "create table t (id uuid primary key default extensions.uuid_generate_v4(), "
        "token text default encode(gen_random_bytes(8), 'hex'));"
    )})
    done = rlsentry(folder)
    assert done.returncode == 1, done.stderr
    assert "read public.t: exposed" in done.stdout


# The guard runs inside the migrations' own session, so it must not resolve a name, a function or
# an operator under their search_path or their temporary objects (verdict D-1 on #25).
SHADOW_EXTENSION = [
    # a view in public, put before pg_catalog, naming every new extension as a listed one
    "set search_path = public, pg_catalog;\n"
    "create view public.pg_extension as select oid, 'pgcrypto'::name as extname from pg_catalog.pg_extension;",
    # a view that finds no row, so the extension's name is null
    "set search_path = public, pg_catalog;\n"
    "create view public.pg_extension as select oid, extname from pg_catalog.pg_extension where false;",
    # a temporary view: pg_temp is searched before pg_catalog, with no search_path change at all
    "create temporary view pg_extension as select oid, 'pgcrypto'::name as extname from pg_catalog.pg_extension;",
    # a function standing in for the event trigger's own
    "set search_path = public, pg_catalog;\n"
    "create function public.pg_event_trigger_ddl_commands() returns table "
    "(classid oid, objid oid, objsubid int, command_tag text, object_type text, schema_name text, "
    "object_identity text, in_extension bool, command pg_ddl_command) "
    "language sql as $$ select null::oid, null::oid, null::int, null::text, null::text, null::text, "
    "null::text, null::bool, null::pg_ddl_command where false $$;",
    # an operator that says every name is unequal to nothing
    "set search_path = public, pg_catalog;\n"
    "create function public.never_ne(text, text) returns bool language sql as 'select false';\n"
    "create operator public.<> (leftarg = text, rightarg = text, function = public.never_ne);",
]


@pytest.mark.parametrize("shadow", SHADOW_EXTENSION)
def test_a_shadowed_catalog_does_not_let_an_extension_through(tmp_path, shadow):
    done = refused(tmp_path, shadow + "\ncreate extension lo;", statement="create extension lo")
    assert 'extension "lo" is not on the list the copy allows' in done.stderr
