"""S-1: the inputs a run is given (#23), the order migrations are applied in, and a failing one."""

import os
import time

from conftest import assert_no_copy_left, records, rlsentry, write


def test_a_folder_without_sql_files_stops(tmp_path):
    folder = write(tmp_path / "p", {"notes.txt": "no migrations here", "schema.SQL.bak": ""})
    before = records()
    done = rlsentry(folder)
    assert done.returncode == 2
    assert f"no .sql file in {folder}" in done.stderr
    assert records() == before
    assert_no_copy_left()


def test_names_equal_but_for_case_stop(tmp_path):
    folder = write(tmp_path / "p", {"001_Init.sql": "create table a (x int);", "001_init.sql": "create table b (x int);"})
    done = rlsentry(folder)
    assert done.returncode == 2
    assert "differ only in case" in done.stderr
    assert "001_Init.sql" in done.stderr and "001_init.sql" in done.stderr
    assert "copy built" not in done.stdout
    assert_no_copy_left()


def test_a_supabase_projects_folder_uses_only_its_migrations_and_says_so(tmp_path):
    folder = write(tmp_path / "p", {
        "supabase/migrations/20240101000000_init.sql": "create table notes (id int primary key);",
        "supabase/seed.sql": "this is not sql and must never be run;",
        "stray.sql": "neither is this;",
    })
    done = rlsentry(folder)
    assert done.returncode == 0, done.stderr
    assert f"using the migrations in {folder / 'supabase' / 'migrations'}" in done.stderr
    assert "copy built from 1 migration(s)" in done.stdout
    assert "public.notes" in done.stdout
    assert_no_copy_left()


def test_the_projects_configuration_names_the_exposed_schemas(tmp_path):
    folder = write(tmp_path / "p", {
        "supabase/config.toml": '[api]\nenabled = true\nschemas = ["public", "api"]\n',
        "supabase/migrations/001.sql": "create schema api; create table api.items (id int); create table public.a (id int);",
    })
    done = rlsentry(folder)
    assert done.returncode == 0, done.stderr
    assert "exposed schemas: public, api" in done.stdout
    assert done.stdout.index("api.items") < done.stdout.index("public.a")


def test_without_configuration_supabases_default_schemas_are_exposed(tmp_path):
    done = rlsentry(write(tmp_path / "p", {"001.sql": "create table a (id int);"}))
    assert "exposed schemas: public, graphql_public" in done.stdout


def test_files_are_applied_in_name_order_and_the_later_ones_effect_shows(tmp_path):
    folder = write(tmp_path / "p", {
        "2_open.sql": "alter table secrets disable row level security;",
        "10_create.sql": "create table secrets (id int primary key, value text);\n"
                         "alter table secrets enable row level security;",
    })
    # Name order, not age: the file applied first is the newer one on disk.
    now = time.time()
    os.utime(folder / "10_create.sql", (now, now))
    os.utime(folder / "2_open.sql", (now - 100, now - 100))
    done = rlsentry(folder)
    assert done.returncode == 0, done.stderr
    assert "public.secrets (row-level security off)" in done.stdout
    assert_no_copy_left()


def test_a_migration_that_fails_stops_the_run_naming_the_file_and_the_statement(tmp_path):
    folder = write(tmp_path / "p", {
        "001_ok.sql": "create table a (id int primary key);",
        "002_bad.sql": "-- adds a column\ncreate table b (id int primary key);\n\n"
                       "alter table b add column owner uuid references missing_table(id);\n"
                       "create table c (id int);",
    })
    done = rlsentry(folder)
    assert done.returncode == 2
    assert "migration 002_bad.sql failed at line 4" in done.stderr
    assert "relation \"missing_table\" does not exist" in done.stderr
    assert "alter table b add column owner uuid references missing_table(id)" in done.stderr
    assert "copy built" not in done.stdout and "public.a" not in done.stdout
    assert_no_copy_left()
