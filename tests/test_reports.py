"""S-1 (reports), S-3 and S-7's last clause: the text summary and the JSON report, both rendered from
one run on a real copy, hold the same facts; a stopped run still reports what it found; a value
from the copy cannot act on the terminal; two runs on the same migrations give the same report."""

import json
import re
import subprocess
from importlib import resources

import jsonschema

from conftest import assert_no_copy_left, outcomes, rlsentry, write
from rlsentry.versions import find


def schema() -> dict:
    """The schema published with rlsentry, as an installed package holds it."""
    return json.loads(resources.files("rlsentry").joinpath("report.schema.json").read_text())


def run_with_report(tmp_path, files: dict[str, str], name: str = "p"):
    report_file = tmp_path / f"{name}.json"
    done = rlsentry(write(tmp_path / name, files), "--json", report_file)
    assert_no_copy_left()
    raw = report_file.read_bytes()
    report = json.loads(raw)
    jsonschema.validate(report, schema())
    return done, report, raw


def program_version(program: str) -> str:
    out = subprocess.run([find(program), "--version"], capture_output=True, text=True).stdout
    return re.search(r"\d+\.\d+(?:\.\d+)?", out).group(0)


ONE_EXPOSED = {"001.sql": "create table notes (id int primary key, body text);"}


def test_the_summary_of_a_run_with_one_exposed_read(tmp_path):
    done = rlsentry(write(tmp_path / "p", ONE_EXPOSED))
    assert done.returncode == 1, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    assert lines[0] == (f"rlsentry 0.1.0: copy built from 1 migration(s) on PostgreSQL {program_version('postgres')} "
                        f"and PostgREST {program_version('postgrest')}")
    assert lines[1] == "exposed schemas: public, graphql_public"
    assert lines[2] == ("read public.notes: exposed; basis: rows came back with the anon key and without a key; "
                        "2 of the table's 2 rows")
    assert lines[3] == '  evidence: {"id": 1, "body": "rlsentry-fake-notes-0"}'
    assert lines[4:] == ["exit 1: at least one read is exposed, and every table got a verdict"]
    assert "evidence" not in done.stderr and "exit 1" not in done.stderr, "progress only on standard error"


SUMMARY_KINDS = re.compile(
    r"rlsentry \S+: copy built from |exposed schemas: |read \S+: (exposed|no verdict); |  evidence: \{"
    r"|partitions of \S+, reached through it: |not reachable over the REST layer with these settings: "
    r"|stopped: |exit [012]: "
)

MIXED = {
    "supabase/config.toml": '[api]\nschemas = ["public"]\n',
    "supabase/migrations/001.sql": (
        "create table a_open (id int primary key, body text);\n"
        "create table b_empty (id int primary key);\nalter table b_empty enable row level security;\n"
        "create table c_people (id int primary key, name text, secret text);\n"
        "revoke all on c_people from anon;\ngrant select (id, name) on c_people to anon;\n"
        "create table d_measures (id int, at date not null) partition by range (at);\n"
        "create table d_measures_2024 partition of d_measures for values from ('2024-01-01') to ('2025-01-01');\n"
        "create table d_measures_old partition of d_measures for values from ('2000-01-01') to ('2024-01-01');\n"
        "create schema private;\ncreate table private.keys (id int);"
    ),
}


def test_the_summary_on_stdout_and_the_stop_on_stderr(tmp_path):
    done = rlsentry(write(tmp_path / "p", MIXED))
    assert done.returncode == 2, done.stdout + done.stderr
    lines = done.stdout.splitlines()
    for line in lines:
        assert SUMMARY_KINDS.match(line), f"not a line of the summary: {line!r}"
    assert "partitions of public.d_measures, reached through it: public.d_measures_2024, public.d_measures_old" in lines
    assert "not reachable over the REST layer with these settings: private.keys" in lines
    assert "read public.b_empty: no verdict; anon key: status 200, the answer held no row; " \
           "no key: status 200, the answer held no row" in lines
    assert lines[-2].startswith("stopped: no verdict for public.b_empty read")
    assert lines[-2].endswith("protected verdicts come with anon-read-protected")
    assert lines[-1] == "exit 2: the run stopped: some table got no verdict"
    assert "stopped: no verdict for public.b_empty read" in done.stderr
    for line in lines[:-2]:
        assert line not in done.stderr, "the summary is not repeated on standard error"


def test_the_json_report_holds_the_facts_of_the_summary(tmp_path):
    done, report, _ = run_with_report(tmp_path, MIXED)
    assert done.returncode == 2 == report["exit_code"]
    assert report["schema_version"] == schema()["properties"]["schema_version"]["const"] == "1.0"
    assert report["versions"] == {"rlsentry": "0.1.0", "postgresql": program_version("postgres"),
                                  "postgrest": program_version("postgrest")}
    lines = done.stdout.splitlines()
    v = report["versions"]
    assert lines[0] == (f"rlsentry {v['rlsentry']}: copy built from {report['migrations']} migration(s) on "
                        f"PostgreSQL {v['postgresql']} and PostgREST {v['postgrest']}")
    assert lines[1] == "exposed schemas: " + ", ".join(report["exposed_schemas"])
    printed = outcomes(done.stdout)
    assert list(printed) == [f"{r['schema']}.{r['table']}" for r in report["results"]]
    for r in report["results"]:
        line = printed[f"{r['schema']}.{r['table']}"]
        assert line["verdict"] == r["verdict"]
        if r["verdict"] == "exposed":
            assert line["text"] == r["basis"]["text"]
            assert line["evidence"] == r["evidence"]
        else:
            assert line["text"] == r["reason"] and r["basis"] is None and r["evidence"] is None
    people = report["results"][2]
    assert people["table"] == "c_people" and people["basis"]["columns"] == ["id", "name"]
    assert people["basis"]["requests"] == ["anon key", "no key"]
    assert report["results"][1]["attempts"][0] == {"key": "anon key", "status": 200, "error_code": None,
                                                   "rows": None, "reason": "the answer held no row"}
    assert report["not_reachable"] == ["private.keys"]
    assert f"not reachable over the REST layer with these settings: private.keys" in lines
    assert report["partitions"] == [{"parent": "public.d_measures",
                                     "partitions": ["public.d_measures_2024", "public.d_measures_old"]}]
    assert report["finished"] is True
    assert lines[-2] == f"stopped: {report['stop']['reason']}" and report["stop"]["table"] is None
    assert lines[-1] == f"exit {report['exit_code']}: {report['exit_meaning']}"


SHAPED = {
    "001.sql": "create table a_open (id int primary key);",
    "002.sql": """
create domain public.shown_text as text;
create function public.shown(public.shown_text) returns json language sql immutable
  as $$ select to_json('not in the table'::text) $$;
create cast (public.shown_text as json) with function public.shown(public.shown_text) as implicit;
create table b_shaped (id int primary key, v public.shown_text);
""",
    "003.sql": "create table c_later (id int primary key);",
}


def test_a_stopped_run_still_reports_what_it_found_in_both_forms(tmp_path):
    done, report, _ = run_with_report(tmp_path, SHAPED)
    assert done.returncode == 2 == report["exit_code"]
    assert [(r["table"], r["verdict"]) for r in report["results"]] == [("a_open", "exposed")], \
        "the tables not judged appear with no verdict and no entry"
    assert report["finished"] is False
    assert report["stop"]["table"] == "public.b_shaped"
    assert report["stop"]["reason"].startswith(
        "the read of public.b_shaped with the anon key answered with a row the table does not hold")
    lines = done.stdout.splitlines()
    assert list(outcomes(done.stdout)) == ["public.a_open"]
    assert lines[-2] == f"stopped at public.b_shaped: {report['stop']['reason']}"
    assert lines[-1] == "exit 2: the run stopped: some table got no verdict"


HOSTILE = "\x1b[2J\x1b[32mprotected\x1b[0m\x9b31m<script>alert(1)</script><b>ok</b>\r\nread public.x: protected"


def test_a_row_value_cannot_take_over_the_terminal(tmp_path):
    literal = HOSTILE.replace("'", "''").replace("\x1b", "' || chr(27) || '").replace("\x9b", "' || chr(155) || '") \
        .replace("\r", "' || chr(13) || '").replace("\n", "' || chr(10) || '")
    done, report, raw = run_with_report(tmp_path, {"001.sql": (
        f"create table notes (id int primary key, shown text generated always as ('{literal}') stored);\n"
        # a name the migrations chose is untrusted too
        "do $$ begin execute format('create table %I (id int)', 'z' || chr(27) || '[2J' || chr(10) || 'forged'); end $$;"
    )})
    assert done.returncode == 1, done.stdout + done.stderr
    out = done.stdout.encode()
    for byte in (b"\x1b", "\x9b".encode(), b"\r"):
        assert byte not in out
        assert byte not in raw
    assert "read public.x: protected" not in done.stdout.splitlines(), "a value cannot forge a line"
    assert "<script>alert(1)</script><b>ok</b>" in done.stdout, "markup is shown as text"
    assert outcomes(done.stdout)["public.notes"]["evidence"]["shown"] == HOSTILE
    assert report["results"][0]["evidence"]["shown"] == HOSTILE
    assert "read public.z\\x1b[2J\\nforged: exposed; basis: " in done.stdout
    assert report["results"][1]["table"] == "z\x1b[2J\nforged"


REPRODUCIBLE = {"001.sql": """
create table events (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  kind text check (kind in ('talk', 'workshop')),
  starts timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamp,
  on_day date,
  data jsonb
);
create table changes (id bigint generated always as identity primary key, at timestamptz default now(), what text);
create function public.touch() returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  new.on_day := current_date;
  insert into public.changes (at, what) values (clock_timestamp(), 'event ' || new.name);
  return new;
end $$;
create trigger touch before insert or update on events for each row execute function public.touch();
create table rooms (id bigint generated always as identity primary key, label varchar(4), size numeric(6, 2));
"""}


def test_two_runs_on_the_same_migrations_give_the_same_report(tmp_path):
    first, one, _ = run_with_report(tmp_path, REPRODUCIBLE, name="one")
    second, two, _ = run_with_report(tmp_path, REPRODUCIBLE, name="two")
    assert first.returncode == second.returncode == 1, first.stdout + first.stderr
    assert [r["table"] for r in one["results"]] == ["changes", "events", "rooms"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", one["ran_at"])
    one.pop("ran_at")
    two.pop("ran_at")
    assert one == two
    assert first.stdout == second.stdout
