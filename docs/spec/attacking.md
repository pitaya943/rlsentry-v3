# Attacking a project

This area says how a user points rlsentry at a project's migrations or at a lab schema, and what one
run does from the command to the exit code.

## Scenarios

"Shown by" names the test that shows a scenario hold; every test builds a real copy and sends real
requests.

### Run rlsentry on a project's migrations

Given a Supabase project's folder whose migrations create three tables, two whose reads an
anonymous visitor gets rows from and one whose read returns nothing,
when the user runs rlsentry on the folder,
then it prints the two exposed verdicts with their basis and evidence, stops on the third naming
the table and saying protected verdicts come with `anon-read-protected`, destroys the copy, and
exits `2`; on a folder with only the two, it exits `1`.
Shown by: `tests/test_attacking.py::test_a_projects_migrations_give_two_exposed_reads_and_a_stop_on_the_third`
and `::test_a_projects_migrations_with_only_exposed_reads_exit_1`.

### Run rlsentry on a plain folder of SQL files

Given a folder holding only `.sql` files whose names give their order, where a later file changes a
table an earlier one created,
when the user runs rlsentry on it,
then the files are applied in name order and the verdicts describe the table as the later file left
it.
Shown by: `tests/test_inputs.py::test_files_are_applied_in_name_order_and_the_later_ones_effect_shows`,
whose later file turns row-level security off and whose read is then exposed.

### A migration that fails stops the run

Given a folder whose second migration has an error,
when the user runs rlsentry on it,
then nothing is attacked, the message names the file and the failing statement, the copy is
destroyed, and the command exits `2`.
Shown by: `tests/test_inputs.py::test_a_migration_that_fails_stops_the_run_naming_the_file_and_the_statement`.

### A table that lets in only requests without a key is exposed

Given a table whose read policy admits rows only when the request's claims hold no issuer,
when the user runs rlsentry,
then its read is exposed, the basis says the rows came back to a request without a key, and the
command exits `1`.
Shown by: `tests/test_verdicts.py::test_a_table_that_lets_in_only_requests_without_a_key_is_exposed`,
whose basis also shows that the same read with the anon key got no row: trying the key alone
would have missed it.

### A table outside `public` in an exposed schema is attacked

Given a project whose Supabase configuration exposes a second schema, and a table in it with
row-level security off on which the migrations grant the schema's use and reads to `anon`,
when the user runs rlsentry,
then that table's read is exposed and the report names it with its schema; without those grants,
the table gets no verdict and the run stops naming the schema, since Supabase grants nothing
outside `public` by default.
Shown by: `tests/test_attacking.py::test_a_table_in_a_second_exposed_schema_is_attacked_when_the_migrations_grant_it`
and `::test_without_the_grants_a_second_schemas_table_gets_no_verdict_naming_the_schema`.

### A table in a schema the API does not expose is named, not attacked

Given a project with a table in a schema its configuration does not expose,
when the user runs rlsentry,
then the table gets no verdict, and the report names it as not reachable over the REST layer with
the project's settings.
Shown by: `tests/test_attacking.py::test_a_table_in_a_schema_the_api_does_not_expose_is_named_not_attacked`.

### Two runs on the same migrations give the same report

Given the same folder of migrations,
when the user runs rlsentry on it twice,
then both runs give the same verdicts, bases and evidence rows, in the same order.
Shown by: `tests/test_reports.py::test_two_runs_on_the_same_migrations_give_the_same_report`, which
compares the two JSON reports apart from the time of the run, and the two summaries.

## Rules

Every rule here was decided by `v3-spec`, except those that name `anon-read-copy`, which decided
them. A rule marked "from `anon-read-protected`" is agreed and not built yet.

### What a run is given

- A folder: either a Supabase project's folder, whose migrations are its `supabase/migrations/*.sql`
  files, or a folder holding only `.sql` files. The files are applied in the order of their names, as
  the Supabase CLI applies a project's migrations. Why: the
  name order is the order the project's own tools apply them in, so the copy is built as the project
  is.
- Or the name of a lab schema, which runs exactly as a folder does (see [the lab](lab.md)).
- A migration that fails stops the run with exit `2`, naming the file and the statement, and the copy
  is destroyed. Why: a copy missing part of its schema is not the project, and a verdict on it would
  describe a database nobody has.
- `--target` is refused, as [live targets](live-targets.md) says.
- Inputs at the edge, decided by `anon-read-copy` (#23): a folder with no `.sql` file stops with
  exit `2` saying so; two migration names that differ only in case stop the run; a folder holding
  `supabase/migrations/` uses only that subfolder and says so; migrations that create no table in an
  exposed schema give an empty report and exit `0`; a table with no columns gets no verdict, named;
  a partitioned table is attacked through its parent only, and the report lists its partitions as
  reached through it. There is no limit on the number of tables or the size of a row. Why: each is
  a case the spec left open, and each answer either says what was not attacked or refuses an input
  the project's own tools would not apply the same way.

### What one run does

In this order: check the programs' versions; build the copy and apply the migrations; read the
settings they made ([the throwaway copy](throwaway-copy.md#the-rest-layers-settings-come-from-rlsentry-alone));
seed; start the REST layer; then for each table in an exposed schema, in order of schema name then
table name, and for each operation the task in hand attacks (read, from `anon-read-copy`), the
check of [the bound](verdicts.md#the-bound-of-a-protected-verdict) (from `anon-read-protected`), the
attempts, and the verdict; then the report; then destroy the copy. Why: a fixed order makes two runs on the same migrations give the
same report, and a table that stops the run stops it at the same place every time.

- Every table is read, both with the anon key and with no key, before the run ends, unless a stop
  that ends the run at once comes first; a table that gets no verdict leaves the remaining tables to
  be attacked ([verdicts](verdicts.md#when-a-run-stops)). Why: one table's unanswered read says
  nothing about the next table, and the user learns every exposed read in one run (`anon-read-copy`).
- Each request has a 30-second timeout; a read that gets no answer in that time gives its table no
  verdict, naming the table (`anon-read-copy`, #23). Why: a policy can make a read hang, and a run
  must end.
- Attempts are sent one at a time, and each is judged before the next is sent. Why: the verdict rules
  judge an attempt against the table as it was just before ([verdicts](verdicts.md#two-verdicts-and-nothing-between-them)).
- A run that stops still writes what it found up to the stop, and its report says it stopped and why
  ([reports](reports.md)).

### What each attempt carries

- Each attempt goes only to the copy's REST layer on loopback, carries nothing that identifies the
  user or the machine, and follows no redirect. Why: [threat model](threat-model.md#what-rlsentry-itself-must-never-do),
  rule 1.
- **Each operation is attempted twice: once with the copy's anon key as the bearer token, and once
  with no key at all.** The operation is exposed when either attempt is, and the basis says which.
  From `anon-read-protected`, it is protected only when both are protected by the verdict rules;
  until then, an operation neither attempt shows exposed gets no verdict. Why: Supabase's REST layer runs a request that carries no key as `anon` too, with claims
  holding only the role, and the migrations cannot say whether the gateway in front of the real
  project lets such a request through. A policy that reads the claims can treat the two differently,
  so reporting protected after trying only one could miss the other; trying both costs one attempt.
- The copy's anon key holds the claims Supabase puts in a project's anon key: `role` `anon`, `iss`
  `supabase`, and a project reference, issue time and expiry rlsentry makes up, the same on every
  run. From `anon-read-protected`, when what decides
  access for an operation reads any claim other than `role`, `iss` and the user id (absent from every
  anon key), or reads the claims other than by naming one, the run stops before that operation is
  attacked, naming the claim. Why: the made-up values differ from the real key's, so a policy that
  compares them could answer one way in the copy and another on the project.
- **Each attempt on a table selects that table's own schema** with the `Accept-Profile` header for a
  read (and `Content-Profile` for a write). The search path the request then runs with is that
  schema followed by `public, extensions`. Why: PostgREST reaches a table only under its own schema's
  name, so the visitor's requests to it carry the same schema and the same search path as rlsentry's;
  a name a policy's function leaves without its schema resolves the same way for both.
- A read attempt asks for exactly the columns `anon` may read, with no filter, range, order or
  limit, and no `Prefer` header. Why: [verdicts](verdicts.md#read) and
  [grants](verdicts.md#grants) require it, so the answer holds every row the policies admit.

### What a run sends nowhere

- rlsentry sends nothing beyond the copy: no update check, no telemetry, no lookup of a name or
  address. Why: [threat model](threat-model.md#what-rlsentry-itself-must-never-do), rule 1, and the
  index's promise.

## Not yet built

Each scenario below is built by the task it is marked with. "Shown by" says how a person or a test
sees it hold. `anon-write` adds insert, update and delete to the same run; `authenticated-attack`
adds a logged-in user; `more-surfaces` adds views, storage buckets and database functions.

### A policy that compares the key's project reference stops the run (`anon-read-protected`)

Given a table whose read policy admits rows only when the claims hold a certain project reference,
when the user runs rlsentry,
then no verdict is given for the read, the message names the table, the policy and the claim, and the
command exits `2`.
Shown by: a test on such a schema checks that no verdict is reported, the message and the exit code.

## Changed by

- `v3-spec`: the first version of this area.
- `anon-read-copy`: the scenarios it built moved up to Scenarios; the inputs a run is given and
  the order of a read's attempts.
