# Attacking a project

This area says how a user points rlsentry at a project's migrations or at a lab schema, and what one
run does from the command to the exit code.

## Scenarios

None hold yet: nothing is built. The scenarios `anon-read` builds are under
[Not yet built](#not-yet-built).

## Rules

Every rule here was decided by `v3-spec`.

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

### What one run does

In this order: check the programs' versions; build the copy and apply the migrations; read the
settings they made ([the throwaway copy](throwaway-copy.md#the-rest-layers-settings-come-from-rlsentry-alone));
seed; start the REST layer; then for each table in an exposed schema, in order of schema name then
table name, and for each operation the task in hand attacks (read, from `anon-read`), the check of
[the bound](verdicts.md#the-bound-of-a-protected-verdict), the attempts, and the verdict; then the
report; then destroy the copy. Why: a fixed order makes two runs on the same migrations give the
same report, and a table that stops the run stops it at the same place every time.

- Attempts are sent one at a time, and each is judged before the next is sent. Why: the verdict rules
  judge an attempt against the table as it was just before ([verdicts](verdicts.md#two-verdicts-and-nothing-between-them)).
- A run that stops still writes what it found up to the stop, and its report says it stopped and why
  ([reports](reports.md)).

### What each attempt carries

- Each attempt goes only to the copy's REST layer on loopback, carries nothing that identifies the
  user or the machine, and follows no redirect. Why: [threat model](threat-model.md#what-rlsentry-itself-must-never-do),
  rule 1.
- **Each operation is attempted twice: once with the copy's anon key as the bearer token, and once
  with no key at all.** The operation is exposed when either attempt is, and the basis says which;
  protected only when both are protected by the verdict rules; when either cannot be shown, the run
  stops. Why: Supabase's REST layer runs a request that carries no key as `anon` too, with claims
  holding only the role, and the migrations cannot say whether the gateway in front of the real
  project lets such a request through. A policy that reads the claims can treat the two differently,
  so reporting protected after trying only one could miss the other; trying both costs one attempt.
- The copy's anon key holds the claims Supabase puts in a project's anon key: `role` `anon`, `iss`
  `supabase`, and a project reference, issue time and expiry rlsentry makes up. When what decides
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

Each scenario below is built by `anon-read`. "Shown by" says how a person or a test sees it hold.
`anon-write` adds insert, update and delete to the same run; `authenticated-attack` adds a logged-in
user; `more-surfaces` adds views, storage buckets and database functions.

### Run rlsentry on a project's migrations (`anon-read`)

Given a Supabase project's folder with migrations that create three tables,
when the user runs rlsentry on the folder,
then it prints, for each table, its read verdict and basis, destroys the copy, and exits `0` if no
read was exposed and `1` if one was.
Shown by: a test runs rlsentry on such a folder and checks each table's verdict, the exit code, and
that the copy is gone.

### Run rlsentry on a plain folder of SQL files (`anon-read`)

Given a folder holding only `.sql` files whose names give their order, where a later file changes a
table an earlier one created,
when the user runs rlsentry on it,
then the files are applied in name order and the verdicts describe the table as the later file left
it.
Shown by: a test whose later file turns row-level security off checks that the read is exposed.

### A migration that fails stops the run (`anon-read`)

Given a folder whose second migration has an error,
when the user runs rlsentry on it,
then nothing is attacked, the message names the file and the failing statement, the copy is
destroyed, and the command exits `2`.
Shown by: a test checks the message, that no verdict is reported, the exit code, and that the copy
is gone.

### A table that lets in only requests without a key is exposed (`anon-read`)

Given a table whose read policy admits rows only when the request's claims hold no issuer,
when the user runs rlsentry,
then its read is exposed, the basis says the rows came back to a request without a key, and the
command exits `1`.
Shown by: a test on such a schema checks the verdict and the basis; a person sends the copy the same
read with the anon key and sees no row, which is why trying the key alone would have said protected.

### A policy that compares the key's project reference stops the run (`anon-read`)

Given a table whose read policy admits rows only when the claims hold a certain project reference,
when the user runs rlsentry,
then no verdict is given for the read, the message names the table, the policy and the claim, and the
command exits `2`.
Shown by: a test on such a schema checks that no verdict is reported, the message and the exit code.

### A table outside `public` in an exposed schema is attacked (`anon-read`)

Given a project whose Supabase configuration exposes a second schema, and a table in it with
row-level security off,
when the user runs rlsentry,
then that table's read is exposed and the report names it with its schema.
Shown by: a test on such a project checks the verdict and the schema named; a person sends the copy
a read for the table without the profile header and sees it refused, and with it sees rows.

### A table in a schema the API does not expose is named, not attacked (`anon-read`)

Given a project with a table in a schema its configuration does not expose,
when the user runs rlsentry,
then the table gets no verdict, and the report names it as not reachable over the REST layer with
the project's settings.
Shown by: a test on such a project checks the report lists the table as not reachable and that no
attempt on it appears in the copy's log.

### Two runs on the same migrations give the same report (`anon-read`)

Given the same folder of migrations,
when the user runs rlsentry on it twice,
then both runs give the same verdicts, bases and evidence rows, in the same order.
Shown by: a test runs twice and compares the two JSON reports, apart from the time of the run.

## Changed by

- `v3-spec`: the first version of this area.
