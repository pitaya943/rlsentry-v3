# The throwaway copy

This area says what database one run builds from a project's migrations, how it is set up to answer
as a Supabase project would, how it is filled with fake rows, where it runs, and how it is destroyed.

## Scenarios

"Shown by" names the test that shows a scenario hold; every test builds a real copy and sends real
requests.

### The copy is gone when a run ends

Given a run that finished, a run stopped with exit `2`, and a run interrupted from the keyboard while
it attacks,
when each has exited,
then no database or REST process of the run is left, its data and socket directories are gone, and
its ports are free.
Shown by: `tests/test_lifecycle.py::test_the_copy_is_gone_however_the_copy_ends`,
`::test_a_finished_run_and_a_stopped_run_leave_nothing`, `::test_ctrl_c_while_running_destroys_the_copy`
and `::test_sigterm_while_running_destroys_the_copy`.

### A copy left by a killed run is removed by the next

Given a run that was killed while its copy was running,
when the user starts another run,
then the new run removes the copy left behind, says that it did, and goes on.
Shown by: `tests/test_lifecycle.py::test_a_copy_left_by_a_killed_run_is_removed_by_the_next`.

### A migration cannot reach the machine

Given a migration that tries to run a program on the machine, read or write a file outside the
database, or create an extension outside the list,
when the user runs rlsentry on it,
then the database refuses the statement, the run stops with exit `2` naming the file and the
statement, the copy is destroyed, and nothing the migration tried exists on the machine.
Shown by: `tests/test_boundary.py` (`test_a_migration_cannot_run_a_program`,
`test_a_migration_cannot_read_a_file`, `test_a_migration_cannot_write_a_file`,
`test_a_psql_command_in_a_migration_is_not_run`, `test_an_extension_outside_the_list_is_refused`),
each aiming at a file the test watches.

### A setting a migration makes for the REST layer stops the run

Given a table whose read policy admits a row only to claims naming that row's owner, and a migration
that makes PostgREST run a function before every request that rewrites the claims from a request
header,
when the user runs rlsentry,
then no verdict is given for the table, the run stops before any attack, its message names the
setting and the role it was put on, and the command exits `2`.
Shown by: `tests/test_settings.py::test_a_per_request_function_set_for_the_rest_layer_stops_the_run`
and `::test_a_rest_layer_setting_anywhere_stops_the_run`.

### A setting a migration puts on the anonymous role stops the run

Given a migration that puts a setting on the role `anon`,
when the user runs rlsentry,
then the run stops before any attack, naming the role and the setting, and exits `2`.
Shown by: `tests/test_settings.py::test_a_setting_on_a_role_a_request_passes_through_stops_the_run`,
for `anon`, `authenticated` and `authenticator`.

### A table created without grants is read as on Supabase

Given a migration that creates a table in `public` with row-level security off and grants nothing
on it,
when the user runs rlsentry,
then the table's read is exposed, because Supabase's default privileges grant it to the anonymous
visitor.
Shown by: `tests/test_seeding.py::test_a_table_created_without_grants_is_read_as_on_supabase`.

### Migrations written for Supabase build

Given migrations that refer to Supabase's users table and to the functions that return the
request's user id and role, and create a listed extension with `if not exists`,
when the user runs rlsentry,
then the copy builds and every table gets a verdict or the run stops for a reason the verdicts
area names, never for a missing part of Supabase's setup.
Shown by: `tests/test_supabase_migrations.py::test_migrations_written_for_supabase_build`.

### Every table is seeded with the values its rules name

Given a table with a foreign key to another table, a check on one column, and a read policy that
admits only rows with a certain value,
when the user runs rlsentry,
then both tables hold fake rows before the attack, every child row points at a parent row, and the
seeded table holds rows both with and without the admitted value.
Shown by: `tests/test_seeding.py::test_every_table_is_seeded_with_the_values_its_rules_name`, which
reads the copy through the direct view after seeding, and runs the same migrations twice and finds
the same rows.

### A PostgreSQL or PostgREST of another release series stops the run

Given a machine whose PostgreSQL is not 16 at 16.15 or later, or whose PostgREST is not 12.2 at
12.2.12 or later,
when the user runs rlsentry,
then nothing is built, the message names the program, the version found and the series needed, and
the command exits `2`; within the series, the run goes ahead and both reports name the exact
versions the copy ran.
Shown by: `tests/test_versions.py`: `test_postgresql_outside_the_series_stops_before_anything_is_built`
and `test_postgrest_outside_the_series_stops_before_anything_is_built` put first on the path a
program that only reports another version (the one stand-in the suite allows);
`test_within_the_series_the_run_names_the_exact_versions` and
`test_the_running_servers_version_decides`.

### Tables that reference Supabase's users are seeded

Given a table whose key references Supabase's users table, as most Supabase projects' profile
tables do,
when the user runs rlsentry,
then the users table holds fake users before the attack, every row of the table points at one of
them, and the table gets a verdict or a stop the verdicts area names, never a stop for an unseeded
parent.
Shown by: `tests/test_seeding.py::test_tables_that_reference_supabases_users_are_seeded`.

### Two runs at once do not meet

Given two runs started at the same moment on different migrations,
when both finish,
then each reports the verdicts of its own migrations only.
Shown by: `tests/test_seeding.py::test_two_runs_at_once_do_not_meet`.

## Rules

Every rule here was decided by `v3-spec`, except those that name `anon-read-copy`, which decided
them.

### What the copy is made of

- **PostgreSQL 16 at 16.15 or later, and PostgREST 12.2 at 12.2.12 or later** (`anon-read-copy`,
  which replaced `v3-spec`'s exact pins of 16.16 and 12.2.12: PostgreSQL 16.15 is what the build
  machine's packages give). On the local-process backend rlsentry uses the programs installed on the
  machine and reads each one's `--version` before building; a version outside its series makes the
  run stop with exit `2`, naming the program, the version found and the series needed. Once the
  copy runs, the version is confirmed from the running server; where the two differ, the server's
  version decides, and one outside the series stops the run. Every form of report names the exact
  versions the copy ran. Why: verdicts rest on where in PostgreSQL's own code a refusal was raised and on how PostgREST turns
  a request into a statement; both can change between releases, so a verdict is only as good as the
  versions it was checked on.
- **Supabase's own setup, before any migration**: the database is named `postgres`; the roles
  `anon`, `authenticated` and `service_role`, and `authenticator`, which logs in, inherits nothing
  and can switch to each of them; the schemas `public` and `extensions`; the parts of the `auth`
  schema migrations commonly name (its users table, and the functions that return the request's user
  id, role and claims), defined as Supabase defines them; and Supabase's default privileges, by which
  every table a migration creates in `public` is granted to `anon`, `authenticated` and
  `service_role` unless a migration revokes it. The copy follows the setup of Supabase's
  `supabase/postgres` image release 15.8.1.x, as far as migrations name it
  (`src/rlsentry/supabase_setup.sql`, `anon-read-copy`); it grants nothing outside `public`, as
  that setup does, so a second schema's tables are reachable only once the migrations grant its use
  and its reads. Why: a project's migrations are written against that setup.
  Above all the default privileges: on Supabase a new table is readable by `anon` until a policy or a
  revoke says otherwise, so a copy without them would report a missing grant where the real project
  has none, a false protected.
- A migration that names a part of Supabase's platform the copy does not have fails, and the run
  stops with exit `2`, naming the file and the statement. Why: carrying on without it would attack a
  database the project never had.
- **The migrations' role** is named `postgres`, as on Supabase, owns what the migrations create, and
  is not a superuser (the [threat model](threat-model.md#what-rlsentry-itself-must-never-do), rule 2,
  says what it lacks and why). It may bypass row-level security, so that seeding can fill tables
  whatever their policies say. Why: bypassing row-level security reaches only rows, never files or
  programs.
- **Extensions**: only `pgcrypto`, `uuid-ossp`, `citext`, `pg_trgm`, `btree_gin`, `btree_gist`,
  `hstore`, `ltree`, `intarray`, `fuzzystrmatch`, `tablefunc` and `isn`, each of which PostgreSQL marks
  safe for a non-superuser to create and none of which reads a file or opens a connection. rlsentry
  creates them in `extensions` before the migrations run, as Supabase does, so a migration's
  `create extension if not exists` finds them there; any other extension is refused by a check
  rlsentry installs as the database's superuser, which the migrations' role cannot remove, and the
  run stops with exit `2`, naming the statement. Why: an extension is code in the database server,
  so the list is the threat model's fixed list made concrete.

### The REST layer's settings come from rlsentry alone

- PostgREST runs with its in-database configuration turned off (`db-config = false`), so no
  `pgrst.*` setting a migration makes (`alter role authenticator set pgrst.db_pre_request = ...`, or
  any of the others PostgREST reads that way, such as its JWT secret, its anonymous role, its exposed
  schemas, its maximum rows or its transaction ending) and no setting a migration puts on a role it
  switches to takes effect. rlsentry's own configuration names no per-request function and no
  pre-configuration function. Why: those settings change, before the request's own statement, who
  the request runs as and what its claims hold (a per-request function can switch role or rewrite
  the claims from a header, review [defect 8](https://github.com/pitaya943/rlsentry-v3/pull/6#issuecomment-7212110573));
  none of that is reached by a table's policies, so the check of
  [the bound](verdicts.md#the-bound-of-a-protected-verdict) would never read it.
- **After the migrations and seeding, before PostgREST starts, rlsentry reads every setting they put
  on the roles `anon`, `authenticated` and `authenticator`, and every `pgrst.*` setting they made
  anywhere.** If there is any, the run stops with exit `2` before any attack, naming the role or
  database, the setting and its value; this holds whether or not the migrations' role was allowed to
  make it. Other settings on the role `postgres` (such as its `search_path`) do not stop the run,
  since no request passes through it (`anon-read-copy`, #23). Seeding comes first because it runs
  the migrations' triggers, the last of their code that runs before the reads. Why: on Supabase those settings do take effect, so a copy that ignores
  them answers differently from the real project, and a per-request function the copy never runs
  could let a header open what the copy reports protected. Turning them off keeps the copy's
  attacks honest; stopping keeps the report honest about the real project.
- Settings a migration puts on the database itself (`alter database postgres set ...`) do apply in
  the copy, as on Supabase, since PostgreSQL applies them to every connection; they are the same for
  every request, and a policy that reads one stops the run under the bound's check.
- PostgREST is started only after the migrations and seeding have finished. Why: it reads the
  schema once at start, and a schema it has not seen would answer differently from the real one.
- PostgREST's other settings: `db-anon-role` is `anon`, as Supabase sets it (what this means for
  requests without a key is in [Attacking a project](attacking.md#what-each-attempt-carries));
  `db-extra-search-path` is `public, extensions`, as Supabase sets it; no maximum row count; the
  query plan and aggregate features off and every transaction committed, PostgREST's own defaults;
  a JWT secret made up for this run and never written anywhere. Why: the copy should answer as a
  fresh Supabase project does; a maximum row count would cut a read short and falsify the basis's
  count; a secret anyone could read would let a visitor sign any claims.

### Exposed schemas

- The copy exposes the schemas the project's own Supabase configuration file lists for its API, when
  the folder holds one; otherwise Supabase's default, `public` and `graphql_public`. A request's
  `Accept-Profile` or `Content-Profile` header can select only one of those; any other is refused
  by PostgREST. Why: these headers are how a visitor reaches a table outside `public`, and the
  configuration file is the only place a project's folder records which schemas its API serves.
- A migration that changes the exposed schemas through a `pgrst.*` setting stops the run (above).
- Every table in an exposed schema is attacked (see [Attacking a project](attacking.md)). Tables in
  other schemas are not attacked, and the report names them as not reachable over the REST layer
  with these settings. Why: the real project's dashboard may expose more schemas than its folder
  records; naming what was not attacked lets the reader see that edge instead of reading silence as
  safety.

### Seeding

- Before the attack, every table in an exposed schema is filled with fake rows, as the migrations'
  role, through the table's own checks, triggers and foreign keys: parents before children, and a
  row a check or trigger refuses is replaced by another. Why: rows refused by the table's own rules
  could never exist in the real project, and a row it accepts is one a real table could hold.
- Each table gets at least two rows, and for every value its policies, checks and column definitions
  name against a column, at least one row holding that value and one holding none of them. Why: a
  policy that admits only some values can be seen letting rows through only if such rows exist, and a
  row outside them shows whether the policy keeps anything out
  ([verdicts](verdicts.md#read)).
- Every value is made up by rlsentry, recognisable as fake, and the same for the same migrations on
  every run. The project's own seed file is never run. Why: a report may hold only rows rlsentry made
  up ([threat model](threat-model.md#what-rlsentry-itself-must-never-do), rule 4), a project's seed
  file may hold real data, and the same rows on every run make a run reproducible for tests and
  teaching.
- A date or time the clock filled during seeding (a default such as `now()`, an `updated_at`
  trigger) is then set to one fixed value, unless it equals a value a rule of the table names
  (`anon-read-copy`). Why: otherwise the evidence would differ between two runs on the same
  migrations; a value a rule names is what a verdict rests on, so it is kept.
- Seeding fills every table of an exposed schema and every table their foreign keys reach,
  Supabase's users table (`auth.users`) first, so a table whose key references it holds rows that
  point at fake users (`anon-read-copy`, #22).
- A table seeding cannot fill is left empty; its read then cannot be shown exposed, and the table
  gets no verdict ([verdicts](verdicts.md#when-a-run-stops)).
- Whether the copy loads Supabase's guard against updates and deletes without a filter is
  `anon-write`'s to decide, since only writes meet it.

### Where it runs, and how it is kept apart

- **The local-process backend** (from `anon-read-copy`) and **the Docker backend** (from
  `docker-backend`). What keeps migration code from the host on each is stated once, in the
  [threat model](threat-model.md#what-rlsentry-itself-must-never-do), rule 2; this area builds what
  it says.
- Each run gets its own data directory, socket directory and loopback ports, chosen free when the run
  starts; two runs at once never share any of them. Why: a run that could reach another run's copy
  could judge the wrong database.
- The direct view connects as rlsentry's own role, reads only the catalog and tables with row-level
  security off, and never calls a function or reads a view the migrations made. Why: it must see
  every row, and it must run none of the migrations' code with privileges they lack.

### How it ends

- The copy (its processes, data directory, sockets and ports) is destroyed however the run ends:
  finished, stopped with exit `2`, failed while building, or interrupted from the keyboard. The run
  waits until the copy is gone before it exits. Why: a copy left running is a deliberately weak
  database on the user's machine ([threat model](threat-model.md#what-rlsentry-itself-must-never-do),
  rule 3).
- When rlsentry is killed so that it cannot clean up, the next run finds copies left by runs no
  longer alive, removes them, and says so. Why: a kill cannot be caught, so the cleanup that rule 3
  needs has to happen on the next chance.

## Not yet built

Each scenario below is built by the task it is marked with. "Shown by" says how a person or a test
sees it hold. The Docker backend is `docker-backend`'s: a user with Docker and no local PostgreSQL or
PostgREST runs the same attack, with the copy in containers that are always removed.

### A table whose grant a migration revokes is protected by the missing grant (`anon-read-protected`)

Given a migration that creates a table in `public` with row-level security off and then revokes
every privilege `anon` holds on it,
when the user runs rlsentry,
then the table's read is protected by a missing grant: the revoked-grant half of
[A table created without grants is read as on Supabase](#a-table-created-without-grants-is-read-as-on-supabase).
Shown by: a test on such a schema checks the verdict and that the basis names the grant.

## Changed by

- `v3-spec`: the first version of this area.
- `anon-read-copy`: the copy built, seeded and destroyed; the accepted release series; the
  settings that stop a run; the scenarios it built moved up to Scenarios.
