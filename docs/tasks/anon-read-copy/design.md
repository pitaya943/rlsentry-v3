# anon-read-copy: design

The brief fixes what a run does; this file fixes the shape the code takes, so tickets built one after
another by different builders fit. Each part names the scenarios it serves. A builder who finds a
part wrong changes it here with a trail row; the scenarios do not change.

## The parts and their boundaries

| Part (module under `src/rlsentry/`) | Owns | Serves |
|---|---|---|
| `cli.py` | argument parsing, the order of a run, the exit code, refusing `--target` before anything else | S-1, S-2, S-5 (live target) |
| `inputs.py` | turning a folder or lab name into an ordered list of migration files and the exposed schemas (`supabase/config.toml` `[api] schemas`, else `public`, `graphql_public`); the input stops of #23 | S-1, S-2, S-4 |
| `versions.py` | reading `--version` of `postgres` and `postgrest`, the accepted series, and the server's own version once running | S-7 |
| `copy.py` (with `pg.py`, `statements.py`) | the throwaway copy: run directory, a free loopback port for PostgREST, `initdb`, the server, Supabase's setup, applying migrations, the settings check, starting PostgREST, destroying all of it however the run ends, and removing copies of dead runs | S-5, S-6 (setup), S-7 (server version) |
| `supabase_setup.sql` (package data) | roles, schemas, `auth.users` and `auth.uid()/role()/jwt()`, default privileges, listed extensions, the extension guard | S-5 |
| `direct.py` | the direct view: the exposed schemas' tables in order, the columns `anon` may read, schema usage, tables not reachable, and a table's rows rendered as PostgREST renders them, calling no code of the migrations' | S-1, S-4, S-5 |
| `seed.py` | the fake rows: order by foreign keys, values the rules name, `auth.users` first | S-5, S-6 |
| `attack.py` | the HTTP requests (anon key and no key, `Accept-Profile`, no redirect, 30 s timeout) and the JWT | S-1, S-4 |
| `verdicts.py` | judging one read from its two answers and the direct view: exposed with basis and evidence, no verdict with status, error code and reason, or a stop at once | S-1, S-2 |
| `report.py` + `report.schema.json` | the one result object, the text summary, the JSON report and its schema, escaping of values from the copy | S-1, S-3 |
| `lab/<schema>/` (package data) | each lab schema: `migrations/*.sql` and `statement.json` | S-8 |

One owner per piece of state: the run's facts live in one result object (`report.Result`) built
by `cli.py` from what `verdicts.py` returns; the text summary and the JSON report are both rendered
from it, never from each other or from separate bookkeeping. The copy's processes, directories and
ports are owned by one `Copy` object; nothing else starts or stops a process.

## Data through one run (S-2 traced)

1. `cli.py` parses; `--target` given means print the refusal and exit `2` before any other step
   (no name lookup: the URL is never parsed into a host and resolved).
2. `inputs.py` lists `supabase/migrations/*.sql` (saying it uses that subfolder) or the folder's
   `*.sql`, sorted by name; no file, or two names equal ignoring case, stops.
3. `versions.py` checks both programs' `--version` against the series; outside it stops, nothing
   built.
4. `Copy.__enter__` removes copies left by dead runs (saying so), makes the run directory, picks
   ports, runs `initdb` with a superuser that is not `postgres` (`rlsentry`), starts the server on a
   socket in the run directory only, confirms the server's version, loads Supabase's setup as the
   superuser, then applies each migration as the role `postgres` (not a superuser; `BYPASSRLS`). A
   failing statement stops, naming the file and the statement.
5. `seed.py` fills `auth.users`, then every table of an exposed schema in foreign-key order. Seeding
   runs the migrations' triggers, so it is still migration code running.
6. The settings check reads `pg_db_role_setting` for every role setting and every `pgrst.*`; the
   rules of the brief's Assumptions decide which stop. It runs after the last moment migration code
   can run as the migrations' role (after seeding), right before PostgREST starts, so nothing a
   migration's code sets escapes it (T-02 verdict 1).
7. `Copy` starts PostgREST (`db-config = false`, `db-anon-role = anon`, the exposed schemas,
   `db-extra-search-path = public, extensions`, a JWT secret made up in memory and passed through
   the environment or a file in the run directory readable only by the run, never kept).
8. For each table of an exposed schema in schema-qualified name order: the columns `anon` may read
   (none: no verdict, no request); usage on the schema (none: no verdict, S-4); else two reads
   through `attack.py`, judged by `verdicts.py` against the direct view.
9. `report.py` renders the summary to stdout and, when asked, the JSON file; `cli.py` picks the exit
   code from the result (`2` beats `1`).
10. `Copy.__exit__` stops PostgREST and the server, waits until they are gone, removes the run
    directory. The same happens on `KeyboardInterrupt`, `SIGTERM` and any exception.

## Boundaries and their types

- `inputs.resolve(arg: str) -> Project(name, migrations: list[Path], exposed_schemas: list[str], notes: list[str])`
- `versions.check(env_path) -> Versions(postgres: str, postgrest: str)`; raises `Stop`.
- `Copy(project) ` context manager: `.direct()` gives a psycopg-free direct-view connection helper
  (see "Talking to PostgreSQL"), `.rest_url`, `.anon_key`, `.versions`.
- `verdicts.judge(table, answers, direct_rows) -> Exposed | NoVerdict`; raises `Stop` for the stops
  that end the run at once.
- `report.Result` holds: versions, exposed schemas, tables not reachable, per-table outcomes in
  order, whether the run finished, the stop (reason, table), the exit code, the time of the run.
- One exception type, `Stop(reason: str, table: str | None)`, for every stop that ends the run;
  `cli.py` catches it once.

## Talking to PostgreSQL and PostgREST

- **No third-party runtime dependency.** The direct view and the migrations go through `pg.py`, a
  small client of PostgreSQL's simple query protocol over the copy's socket (`Copy.connect(user)`;
  build JSON with `json_agg` in SQL where a result needs structure), and HTTP through
  `http.client`. (T-01 replaced `psql`: it acts on backslash commands inside a migration file, so
  `\! <command>` in a migration would run on the machine; the server's protocol carries SQL only.) Why: fewer things to install in a tool meant for teaching, and
  `http.client` never follows redirects on its own, which is the rule we need. Tests may use
  `pytest` and `jsonschema` as development dependencies.
- **Migrations are applied statement by statement, each file in one transaction,** as the role
  `postgres`, as the Supabase CLI does: `statements.py` cuts a file at top-level `;` (honouring
  quotes, dollar quotes, comments and `BEGIN ATOMIC` bodies), so a failure names the exact
  statement and its line even where the server's error carries no position (a refused
  `COPY ... TO '<file>'`). A wrong cut can only make a piece fail, which stops the run.

## Running as root

PostgreSQL refuses to start as root, and this session (and many containers) runs as root. When the
effective user is root, `Copy` runs `initdb`, `postgres` and `postgrest` as an unprivileged
account (the existing `postgres` system account if there is one, else `nobody`), through
`subprocess`'s `user`/`group`/`extra_groups`, and gives that account alone the run directory (mode
`0700`). When not root, it runs them as the user. Why: this narrows what the server process can
touch, which is the threat model's rule 2 for local processes, instead of widening it; refusing root
would make the tool unusable in the very environment the brief names.

## Where a run lives, and finding dead runs

Each run gets `<tmp>/rlsentry-runs-<uid>/<run-id>/` holding `data/`, `sock/` and the programs'
logs, and, beside it, `<run-id>.json` (the pid of the rlsentry process and its start time, the
server's and PostgREST's pids and start times, PostgREST's port), written before the directory and
outside it, so the server's account, which owns the directory, cannot change what a later run
kills. The parent directory is created `0700` (or `0711` when root, so the server account can
reach its own run directory). A later run treats a record whose rlsentry pid is not alive (or alive
with another start time) as dead: it stops that run's server (`SIGQUIT`) and PostgREST if they are
still the processes the record names, kills any process still working in its directory
(PostgreSQL's backends each start a session of their own, so process groups do not reach them),
removes the directory, and prints which run it removed. The database server listens on no TCP
port: only its socket, in the run's `0700` socket directory, with `trust` for local connections
only; PostgREST reaches it there. PostgREST's configuration is its environment, not a file. Ports are
chosen by binding port `0` on `127.0.0.1` and releasing it right before start; a start that fails
on a taken port retries with new ports. Two runs never share a directory, socket or port.

## Supabase's setup in the copy

Loaded as the superuser before any migration, from `supabase_setup.sql`, following Supabase's
`supabase/postgres` image setup of the 15.x line as far as migrations name it (the builder records
the release followed in `docs/spec/throwaway-copy.md`, as the spec asks):

- roles `anon`, `authenticated`, `service_role` (`NOLOGIN`), `authenticator` (`LOGIN NOINHERIT`,
  member of the three), `postgres` (`LOGIN`, `CREATEROLE`, `CREATEDB` off, `BYPASSRLS`, not a
  superuser, member of none of `pg_execute_server_program`, `pg_read_server_files`,
  `pg_write_server_files`); schemas `public`, `extensions`, `auth`, `graphql_public`;
- `auth.users` with the columns migrations commonly name (`id uuid primary key`, `email`, `phone`,
  `role`, `aud`, `raw_user_meta_data`, `raw_app_meta_data`, `created_at`, `updated_at`), and
  `auth.uid()`, `auth.role()`, `auth.jwt()` as Supabase defines them over `request.jwt.claim(s)`;
- default privileges `for role postgres in schema public` granting all on tables, sequences and
  functions to `anon`, `authenticated`, `service_role`; usage on `public` to the three;
- the listed extensions created in `extensions`; an event trigger owned by the superuser on
  `ddl_command_end` for `CREATE EXTENSION` that refuses any other, which `postgres` cannot drop;
  `plpgsql` only, no untrusted language.

The copy must answer as Supabase does for grants outside `public` (S-4, #22): no default grant on a
second schema, so the migrations must grant usage and select themselves.

## Seeding

Catalog-driven, never by reading migration text: for each table, the columns and types, `NOT NULL`,
defaults, foreign keys, unique keys and checks from `pg_catalog`; the values its rules name are the
constants (`pg_get_expr` of checks and of policy `USING` expressions, parsed only for
`<column> <op> <constant>` and `<column> in (...)` shapes) compared against a column. At least two
rows per table; for every named value one row holding it and one holding none of them. Values are
fake and recognisable (`rlsentry-fake-<table>-<n>`, uuids from a fixed namespace with `uuid5`), the
same for the same migrations. Parents before children; a row a check or trigger refuses is replaced
by another, bounded tries; a table that still cannot be filled is left empty (its read then has no
verdict). `auth.users` gets fake users first (S-6), and every foreign key to it points at one.

## Judging a read (this task's half)

The two answers (anon key, no key) are judged one at a time:

| Answer | Result |
|---|---|
| a redirect status (`3xx`) | stop at once (S-1 *A redirect is never followed*) |
| `200` with ≥1 row, every row matching a direct-view row on its columns | that request got rows |
| `200` with any row the direct view does not hold | stop at once (S-1) |
| anything else (`200 []`, `401`, `403`, an error, a timeout) | that request did not show exposed |

Exposed when either request got rows; the basis names which (with the key, without a key, both),
how many of the table's rows, and the columns when the grant covers only some. The evidence is one
matched row as the direct view holds it, limited to those columns. Otherwise the table gets no
verdict, with its two statuses, PostgreSQL error code (from the response body's `code` or the copy's
log) and reason; after every table the run stops with exit `2` saying protected verdicts come with
`anon-read-protected`. Reading the direct view and both answers happens with nothing else writing.

## The second shape weighed

**Docker or a vendored `pg_tmp`-style helper instead of our own `Copy`.** Rejected: Docker is
`docker-backend`'s and there is no daemon here (trail, owner answer 2.a); a helper script would split
the cleanup rules between two places. **Parsing migration SQL to seed and to find settings.**
Rejected: the spec says verdicts rest on running, and the catalog already holds what the migrations
built, including what a `DO` block did; reading SQL text would miss that. **A Python PostgreSQL
driver (psycopg).** Considered: simpler result handling, but one more compiled dependency to install
and nothing it gives that `pg.py` with JSON output does not; a builder may switch with a trail row
if `pg.py` proves too clumsy.

## Testing

`pytest` under `tests/`, every test building a real copy; a session-scoped check at the start fails
the whole suite (not skips) naming the program when `postgres`, `initdb` or `postgrest` is
missing (S-10). S-7's only stand-in is a script on `PATH` that prints another version. Lab tests
compare each schema's run with its `statement.json`. `test_command` becomes
`python3 -m pytest -q` (or what the builder records).
