"""S-1 (attacking), S-2 and S-4: which tables a run attacks, in what order, and its exit code."""

from conftest import run

THREE = {
    "supabase/migrations/20240101000000_open.sql": "create table notes (id int primary key, body text);",
    "supabase/migrations/20240102000000_policy.sql": (
        "create table posts (id int primary key, title text);\n"
        "alter table posts enable row level security;\n"
        "create policy \"anyone reads\" on posts for select using (true);"
    ),
}
NOTHING = {
    "supabase/migrations/20240103000000_closed.sql": (
        "create table accounts (id int primary key, owner uuid);\n"
        "alter table accounts enable row level security;\n"
        "create policy \"own\" on accounts for select using (owner = auth.uid());"
    ),
}


def test_a_projects_migrations_give_two_exposed_reads_and_a_stop_on_the_third(tmp_path):
    done, found = run(tmp_path, {**THREE, **NOTHING})
    assert done.returncode == 2, done.stdout + done.stderr
    assert list(found) == ["public.accounts", "public.notes", "public.posts"]
    for name in ("public.notes", "public.posts"):
        assert found[name]["verdict"] == "exposed"
        assert "rows came back with the anon key and without a key" in found[name]["text"]
        assert found[name]["evidence"]["id"] in (1, 2)
    assert found["public.accounts"]["verdict"] is None
    assert "no verdict for public.accounts read" in done.stderr
    assert "protected verdicts come with anon-read-protected" in done.stderr


def test_a_projects_migrations_with_only_exposed_reads_exit_1(tmp_path):
    done, found = run(tmp_path, THREE)
    assert done.returncode == 1, done.stdout + done.stderr
    assert [o["verdict"] for o in found.values()] == ["exposed", "exposed"]


def test_no_table_in_an_exposed_schema_exits_0(tmp_path):
    done, found = run(tmp_path, {
        "supabase/config.toml": '[api]\nschemas = ["public"]\n',
        "supabase/migrations/001.sql": "create schema private;\ncreate table private.keys (id int);",
    })
    assert done.returncode == 0, done.stdout + done.stderr
    assert found == {}


def test_a_table_in_a_schema_the_api_does_not_expose_is_named_not_attacked(tmp_path):
    done, found = run(tmp_path, {
        "supabase/config.toml": '[api]\nschemas = ["public"]\n',
        "supabase/migrations/001.sql": (
            "create schema private;\ncreate table private.keys (id int);\n"
            "grant usage on schema private to anon;\ngrant select on private.keys to anon;\n"
            "create table public.open (id int);"
        ),
    })
    assert done.returncode == 1, done.stdout + done.stderr
    assert list(found) == ["public.open"]
    assert "not reachable over the REST layer with these settings: private.keys" in done.stdout


SECOND_SCHEMA = {
    "supabase/config.toml": '[api]\nschemas = ["public", "api"]\n',
    "supabase/migrations/001.sql": "create schema api;\ncreate table api.items (id int primary key, name text);",
}


def test_a_table_in_a_second_exposed_schema_is_attacked_when_the_migrations_grant_it(tmp_path):
    files = dict(SECOND_SCHEMA)
    files["supabase/migrations/002_grants.sql"] = "grant usage on schema api to anon;\ngrant select on api.items to anon;"
    done, found = run(tmp_path, files)
    assert done.returncode == 1, done.stdout + done.stderr
    assert found["api.items"]["verdict"] == "exposed"
    assert found["api.items"]["evidence"]["name"].startswith("rlsentry-fake-items-")


def test_without_the_grants_a_second_schemas_table_gets_no_verdict_naming_the_schema(tmp_path):
    done, found = run(tmp_path, SECOND_SCHEMA)
    assert done.returncode == 2, done.stdout + done.stderr
    assert found["api.items"]["verdict"] is None
    assert "anon is not granted usage on schema api" in found["api.items"]["text"]
    assert "api.items" in done.stderr and "schema api" in done.stderr


REPRODUCIBLE = {"001.sql": """
create table events (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  kind text check (kind in ('talk', 'workshop')),
  starts timestamptz,
  created_at timestamptz not null default now(),
  data jsonb
);
create table rooms (id bigint generated always as identity primary key, label varchar(4), size numeric(6, 2));
"""}


def test_two_runs_on_the_same_migrations_give_the_same_outcomes_in_the_same_order(tmp_path):
    first, found = run(tmp_path, REPRODUCIBLE, name="one")
    second, again = run(tmp_path, REPRODUCIBLE, name="two")
    assert first.returncode == second.returncode == 1, first.stdout + first.stderr
    assert list(found) == ["public.events", "public.rooms"]
    assert found == again
    assert first.stdout == second.stdout
