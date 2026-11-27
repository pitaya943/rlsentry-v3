# rlsentry

rlsentry builds a throwaway copy of a Supabase project from its migrations, on this machine, and
reads every table the REST layer exposes as the anonymous visitor would. A read it calls exposed
rests on rows the copy really sent back, shown as evidence; the copy is destroyed when the run ends.

## Install

rlsentry needs Python 3.10 or later, PostgreSQL 16 (16.15 or later) and PostgREST 12.2 (12.2.12 or
later) on the path. PostgreSQL's `postgres` and `initdb` are also found through `pg_config --bindir`.
From a checkout of this repository:

```sh
pip install -e .[test]
```

## Run

```sh
rlsentry path/to/project              # a Supabase project's folder, or a folder of .sql files
rlsentry path/to/project --json report.json
```

The summary goes to standard output, and to `--json FILE` the JSON report, which follows
`src/rlsentry/report.schema.json`. The exit code says what the run found: `0` no read exposed, `1`
at least one read exposed, `2` the run stopped (some table got no verdict, or the copy could not be
trusted); the summary's last line says which. A live project (`--target`) is refused.

## The lab

The lab holds small projects flawed on purpose, each named for its flaw, so you can see what
rlsentry says without a project of your own.

```sh
rlsentry lab                          # each schema with its flaw, in one line; builds nothing
rlsentry lab rls-left-off             # run one by name, exactly as a folder is run
rlsentry lab rls-left-off --json report.json
```

Each schema's folder, `src/rlsentry/lab/<name>/`, holds its `migrations/` and a `statement.json`
that says its flaw and the verdicts, exit code and any stop the run gives; the tests check every
schema against it. (A folder of your own named `lab` is run as `rlsentry ./lab`.)

## Test

The tests build real copies, so they need PostgreSQL and PostgREST as above; without them the suite
fails naming what is missing.

```sh
python3 -m pytest -q
```
