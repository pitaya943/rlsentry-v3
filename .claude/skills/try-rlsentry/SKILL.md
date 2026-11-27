---
name: try-rlsentry
description: Use to run rlsentry as a user does (on a folder of migrations, on a lab schema, with a JSON report) and capture the transcript as evidence. Don't use to run the test suite: that is `python3 -m pytest -q`.
---

# Try rlsentry

## Surface

A command-line tool, `rlsentry`. It takes a folder of Supabase migrations (or `rlsentry lab NAME`),
builds a throwaway PostgreSQL + PostgREST copy on this machine, reads every exposed table as the
anonymous visitor, prints a text summary to stdout, the stop (if any) to stderr, and exits
`0` (nothing exposed), `1` (something exposed) or `2` (stopped). `--json FILE` also writes the JSON
report. There is no server to start yourself: each run starts and destroys its own copy, on ports it
picks (loopback only), under `$TMPDIR/rlsentry-runs-<uid>/`.

## Run

Needs Python 3.10+, PostgreSQL 16 (`postgres`, `initdb` on the path or via `pg_config --bindir`) and
PostgREST 12.2 on the path. From the repository root:

```sh
pip install -e .[test]
rlsentry lab                                 # list the lab; builds nothing
```

## Drive

Use `drive.py` beside this file: it runs rlsentry once, prints stdout, stderr and the exit code, and
exits non-zero if the exit code is not the one expected or anything of the run is left behind.

```sh
S=.claude/skills/try-rlsentry
python3 $S/drive.py 0 lab                                   # list the lab
python3 $S/drive.py 1 lab rls-left-off                      # run a lab schema by name
python3 $S/drive.py 1 lab rls-left-off --json /tmp/r.json   # also write the JSON report
python3 $S/drive.py 2 lab policy-before-table               # a migration that fails stops the run
python3 $S/drive.py 1 path/to/folder                        # a folder of your own .sql files
python3 $S/drive.py 2 --target https://example.supabase.co  # a live target is refused
```

To try a project of your own, write a folder with `.sql` files (or `supabase/migrations/*.sql`) and
pass it. Interrupting a run: start `rlsentry` in the background, send `SIGINT` or `SIGTERM` while it
attacks, and check that nothing is left in `$TMPDIR/rlsentry-runs-<uid>/` and no `postgres` or
`postgrest` process works there (`drive.py`'s `left_behind` does that check).

## Observe

Capture the command, the commit (`git rev-parse --short HEAD`), the exit code and the summary lines
that show the result (`read <schema>.<table>: exposed; basis: ...`, its `evidence:` line, the
`exit N:` line, and any `rlsentry: stopped:` line on stderr). For JSON, the `results` entries and
`exit_code`. Commit only those lines; put a long transcript in a collapsed block of a comment.

## Known limits

- The live target is only refused; nothing can be driven against a real project.
- Ctrl-C in a real terminal (the whole foreground process group getting SIGINT) is closest to a
  person's check; a script approximates it with a signal to rlsentry's process group.
- Run as root, the copy runs as the `postgres` (or `nobody`) account; a folder that account cannot
  reach is still fine, since rlsentry reads migrations itself.
