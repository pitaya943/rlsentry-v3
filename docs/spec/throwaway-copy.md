# The throwaway copy

This area says what database one run builds from a project's migrations, how it is set up to answer
as a Supabase project would, how it is filled with fake rows, where it runs, and how it is destroyed.

## Scenarios

None hold yet: nothing is built. The scenarios `anon-read` builds are under
[Not yet built](#not-yet-built).

## Rules

Every rule here was decided by `v3-spec`.

### What the copy is made of

- **PostgreSQL 16.16 and PostgREST 12.2.12**, exactly these. On the local-process backend rlsentry
  uses the programs installed on the machine and checks their versions before building; a different
  version makes the run stop with exit `2`, naming the program, the version found and the one needed.
  Why: verdicts rest on where in PostgreSQL's own code a refusal was raised and on how PostgREST turns
  a request into a statement; both can change between releases, so a verdict is only as good as the
  versions it was checked on.
- **Supabase's own setup, before any migration**: the database is named `postgres`; the roles
  `anon`, `authenticated` and `service_role`, and `authenticator`, which logs in, inherits nothing
  and can switch to each of them; the schemas `public` and `extensions`; the parts of the `auth`
  schema migrations commonly name (its users table, and the functions that return the request's user
  id, role and claims), defined as Supabase defines them; and Supabase's default privileges, by which
  every table a migration creates in `public` is granted to `anon`, `authenticated` and
  `service_role` unless a migration revokes it. The `anon-read` task names, in this area, the release
  of Supabase's setup the copy follows. Why: a project's migrations are written against that setup.
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
- **After the migrations, rlsentry reads every setting they put on a role, and every `pgrst.*`
  setting they made anywhere.** If there is any, the run stops with exit `2` before any attack,
  naming the role or database, the setting and its value; this holds whether or not the migrations'
  role was allowed to make it. Why: on Supabase those settings do take effect, so a copy that ignores
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
- A table seeding cannot fill is left empty; its read then cannot be shown and the run stops, as
  [verdicts](verdicts.md#read) says.
- Whether the copy loads Supabase's guard against updates and deletes without a filter is
  `anon-write`'s to decide, since only writes meet it.

### Where it runs, and how it is kept apart

- **The local-process backend** (from `anon-read`) and **the Docker backend** (from
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

### The copy is gone when a run ends (`anon-read`)

Given a run that finished, a run stopped with exit `2`, and a run interrupted from the keyboard while
it attacks,
when each has exited,
then no database or REST process of the run is left, its data and socket directories are gone, and
its ports are free.
Shown by: a test runs each case, noting the run's processes, directories and ports while it runs,
and checks afterwards that none remains.

### A copy left by a killed run is removed by the next (`anon-read`)

Given a run that was killed while its copy was running,
when the user starts another run,
then the new run removes the copy left behind, says that it did, and goes on.
Shown by: a test kills a run mid-attack, checks its copy is still there, starts a new run and checks
the old copy's processes and directories are gone and the message names them.

### A migration cannot reach the machine (`anon-read`)

Given a migration that tries to run a program on the machine, read or write a file outside the
database, or create an extension outside the list,
when the user runs rlsentry on it,
then the database refuses the statement, the run stops with exit `2` naming the file and the
statement, the copy is destroyed, and nothing the migration tried exists on the machine.
Shown by: a test with one migration per attempt (each aiming at a file the test watches) checks the
exit code, the message, and that the watched file was neither created nor read.

### A setting a migration makes for the REST layer stops the run (`anon-read`)

Given a table whose read policy admits a row only to claims naming that row's owner, and a migration
that makes PostgREST run a function before every request that rewrites the claims from a request
header,
when the user runs rlsentry,
then no verdict is given for the table, the run stops before any attack, its message names the
setting and the role it was put on, and the command exits `2`.
Shown by: a test on such a schema checks that no verdict is reported, the message and the exit code;
a person sends the copy a read with that header while the run waits and sees no row come back,
because the copy never runs the function.

### A setting a migration puts on the anonymous role stops the run (`anon-read`)

Given a migration that puts a setting on the role `anon`,
when the user runs rlsentry,
then the run stops before any attack, naming the role and the setting, and exits `2`.
Shown by: a test on such a schema checks the message and the exit code.

### A table created without grants is read as on Supabase (`anon-read`)

Given a migration that creates a table in `public` with row-level security off and grants nothing
on it,
when the user runs rlsentry,
then the table's read is exposed, because Supabase's default privileges grant it to the anonymous
visitor.
Shown by: a test on such a schema checks the verdict; the same test with a migration that revokes
the grant checks the read is protected by a missing grant.

### Migrations written for Supabase build (`anon-read`)

Given migrations that refer to Supabase's users table and to the functions that return the
request's user id and role, and create a listed extension with `if not exists`,
when the user runs rlsentry,
then the copy builds and every table gets a verdict or the run stops for a reason the verdicts
area names, never for a missing part of Supabase's setup.
Shown by: a test on a lab schema written that way checks the run reaches the attack.

### Every table is seeded with the values its rules name (`anon-read`)

Given a table with a foreign key to another table, a check on one column, and a read policy that
admits only rows with a certain value,
when the user runs rlsentry,
then both tables hold fake rows before the attack, every child row points at a parent row, and the
seeded table holds rows both with and without the admitted value.
Shown by: a test reads the copy through the direct view after seeding and checks the rows; and runs
the same migrations twice and checks the seeded rows are the same.

### The wrong PostgreSQL or PostgREST stops the run (`anon-read`)

Given a machine whose PostgreSQL or PostgREST is not the pinned version,
when the user runs rlsentry,
then nothing is built, the message names the program, the version found and the version needed, and
the command exits `2`.
Shown by: a test that puts a program reporting another version first on the path checks the message
and the exit code.

### Two runs at once do not meet (`anon-read`)

Given two runs started at the same moment on different migrations,
when both finish,
then each reports the verdicts of its own migrations only.
Shown by: a test starts two runs on lab schemas with opposite verdicts at once and checks each
report.

## Changed by

- `v3-spec`: the first version of this area.
