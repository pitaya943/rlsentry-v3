"""S-5: a setting a migration makes for the REST layer, or puts on a role a request passes through,
stops the run before any attack; other settings on `postgres`, and on the database, do not."""

import pytest

from conftest import assert_no_copy_left, rlsentry, write

OWNER_TABLE = """
create table notes (id int primary key, owner uuid not null, body text);
alter table notes enable row level security;
create policy "owner reads" on notes for select using (owner = auth.uid());
"""

PRE_REQUEST = """
create function public.claims_from_header() returns void language plpgsql as $$
begin
  perform set_config('request.jwt.claims',
    json_build_object('role', 'anon', 'sub', current_setting('request.headers', true)::json ->> 'x-user')::text,
    true);
end $$;
alter role authenticator set pgrst.db_pre_request = 'public.claims_from_header';
"""


def stopped(tmp_path, files):
    done = rlsentry(write(tmp_path / "p", files))
    assert done.returncode == 2, done.stdout + done.stderr
    assert "copy built" not in done.stdout and "public.notes" not in done.stdout
    assert_no_copy_left()
    return done.stderr


def test_a_per_request_function_set_for_the_rest_layer_stops_the_run(tmp_path):
    err = stopped(tmp_path, {"001_notes.sql": OWNER_TABLE, "002_hook.sql": PRE_REQUEST})
    assert "pgrst.db_pre_request = 'public.claims_from_header' on role authenticator" in err


@pytest.mark.parametrize("role, setting, value", [
    ("anon", "statement_timeout", "'5s'"),
    ("anon", "search_path", "public, private"),
    ("authenticated", "statement_timeout", "'8s'"),
    ("authenticator", "lock_timeout", "'1s'"),
])
def test_a_setting_on_a_role_a_request_passes_through_stops_the_run(tmp_path, role, setting, value):
    err = stopped(tmp_path, {"001_notes.sql": OWNER_TABLE, "002.sql": f"alter role {role} set {setting} = {value};"})
    assert f"{setting} = " in err and f"on role {role}" in err


@pytest.mark.parametrize("sql, named", [
    ("alter role postgres set pgrst.db_schemas = 'public, private'", "pgrst.db_schemas = 'public, private' on role postgres"),
    ("alter database postgres set pgrst.jwt_secret = 'known'", "pgrst.jwt_secret = 'known' on database postgres"),
    ("alter role anon in database postgres set work_mem = '1MB'", "work_mem = '1MB' on role anon in database postgres"),
])
def test_a_rest_layer_setting_anywhere_stops_the_run(tmp_path, sql, named):
    err = stopped(tmp_path, {"001_notes.sql": OWNER_TABLE, "002.sql": sql + ";"})
    assert named in err


def test_other_settings_on_postgres_and_on_the_database_do_not_stop(tmp_path):
    done = rlsentry(write(tmp_path / "p", {
        "001_notes.sql": OWNER_TABLE,
        "002.sql": "alter role postgres set search_path = public, extensions;\n"
                   "alter role postgres set statement_timeout = '60s';\n"
                   "alter database postgres set work_mem = '8MB';\n"
                   "alter role service_role set statement_timeout = '30s';",
    }))
    # Not stopped by the settings: the table is read (and, its policy admitting no visitor, gets no verdict).
    assert "the migrations make settings" not in done.stderr
    assert done.returncode == 2, done.stderr
    assert "read public.notes: no verdict" in done.stdout
    assert "protected verdicts come with anon-read-protected" in done.stderr
    assert_no_copy_left()


# The settings check runs on its own connection, but a migration owns the database, so the
# database's own settings would reach that connection (verdict D-2 on #25).
@pytest.mark.parametrize("shadow", [
    "alter database postgres set search_path = public, pg_catalog;\n"
    "create view public.pg_db_role_setting as select setdatabase, setrole, setconfig "
    "from pg_catalog.pg_db_role_setting where false;",
    "alter database postgres set search_path = public, pg_catalog;\n"
    "create view public.pg_roles as select rolname, oid from pg_catalog.pg_roles where rolname <> 'anon';",
    # an operator in public, found before the catalog's, that no role's oid equals
    "create function public.never_eq(oid, oid) returns bool language sql as 'select false';\n"
    "create operator public.= (leftarg = oid, rightarg = oid, function = public.never_eq);\n"
    "alter database postgres set search_path = public, pg_catalog;",
])
def test_the_database_settings_a_migration_makes_do_not_blind_the_settings_check(tmp_path, shadow):
    err = stopped(tmp_path, {"001_notes.sql": OWNER_TABLE, "002.sql": "alter role anon set statement_timeout = '1s';",
                             "003.sql": shadow})
    assert "statement_timeout = '1s' on role anon" in err


SEEDING_TRIGGER = """
create table notes (id int primary key, body text);
create function public.late() returns trigger language plpgsql as $$
begin
  execute 'alter role anon set statement_timeout = ''5s''';
  execute 'alter database postgres set pgrst.db_schemas = ''public''';
  return new;
end $$;
create trigger late before insert on notes for each row execute function public.late();
"""


def test_settings_a_migrations_trigger_makes_while_the_copy_is_seeded_stop_the_run(tmp_path):
    # Seeding runs the migrations' triggers: what they set is migration code's doing all the same.
    err = stopped(tmp_path, {"001_notes.sql": SEEDING_TRIGGER})
    assert "statement_timeout = '5s' on role anon" in err
    assert "pgrst.db_schemas = 'public' on database postgres" in err
