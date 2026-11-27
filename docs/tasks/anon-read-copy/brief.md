# anon-read-copy: the first run that reads as the anonymous visitor

## Goal

A user points rlsentry at a folder of Supabase migrations, or at a lab schema by name, and gets,
for every table the project's REST layer exposes, whether an anonymous visitor really read rows
from a throwaway copy built on this machine, with the row as evidence, as a text summary and a JSON
report, and an exit code a script can act on. The copy is always destroyed, nothing in a migration
reaches the machine, and a live target is refused.

This is the first half of what `docs/spec/` marks `anon-read`; the roadmap splits it (owner, this
task's agreeing). This half gives only the *exposed* verdict for a read. A read that is not shown
exposed is not yet called protected: the run stops on it with exit `2` and says that protected
verdicts come with `anon-read-protected`. That keeps the two-verdict model honest while half of it
is built.

### How a run goes in this task

- Tables are attacked in the order of their schema-qualified name. Every table is read, both with
  the anon key and with no key, before the run ends.
- A read is **exposed** when either request gets rows back that the copy really holds; the basis
  says which request got them (with the key, without a key, or both).
- Any other answer (an empty `200`, a `401` or `403`, a permission error, anything else) gives that
  table no verdict. After every table is tried, the run reports the exposed ones, then stops with
  exit `2`, listing each table without a verdict, the answer it got, and that protected verdicts
  come with `anon-read-protected`. A run where every table is exposed exits `1`; one with no table
  in an exposed schema exits `0`.

### Words this brief uses

- **a stop**: the run ends with exit `2` without a verdict for some table, saying why (the
  verdicts area of `docs/spec/` lists the reasons).
- **D-1**: the owner's decision in `docs/tasks/v3-spec/design.md` that *protected* covers only the
  request shapes the verdicts area lists.
- **a lab schema's statement**: the expected verdicts, exit code and stops written in the lab
  schema's own file, which its test compares the run against.
- **Supabase's users table**: `auth.users`, of which the copy needs the columns migrations refer to.
- **meet** (two runs): share a copy, a port, a directory or a process.
- **a pitfall's count**: how many times `.shilaycow/pitfalls.md` records the mistake.

## Out of scope

- The protected verdict for a read, the check before attacking that bounds it (design D-1 of
  `v3-spec`), and the stops that check makes. These are `anon-read-protected`'s, with #14 and #21,
  and with the correction of the pitfall "a protected rule that holds only for the attempts it
  happens to list" (count 5) as a guard in code that replays every past instance.
- The scenarios of `docs/spec/` marked `anon-read` that rest on those: listed under S-9 below.
- Insert, update and delete (`anon-write`); the Docker backend (`docker-backend`); the HTML report
  (`html-report`).
- Installing PostgREST: the cloud environment's setup script does it (the owner adds it; see
  Assumptions).

## Scenarios

Each spec scenario named below is under Not yet built in its area today, marked `anon-read`; this
task builds it and moves it up to Scenarios, as written there unless this brief changes it. Spec
paths are `docs/spec/<area>.md`.

### S-1: Run rlsentry on migrations and get exposed reads (attacking, verdicts, reports: new)

Built as in the spec: *Run rlsentry on a plain folder of SQL files*, *A migration that fails stops
the run*, *A table that lets in only requests without a key is exposed*, *A table in a schema the
API does not expose is named, not attacked*, *Two runs on the same migrations give the same report*
(attacking); *Read a table that has row-level security off*, *Read a table whose policy lets
everyone read*, *Read a table whose policy lets some rows through*, *Read a table whose read grant
covers only some columns*, *An answer holding rows the table does not hold stops the run*, *A
redirect is never followed*, *A run that finds something and then stops exits 2* (verdicts); *Read
the JSON report from a script*, *A stopped run still reports what it found*, *A row value cannot
take over the terminal* (reports).

### S-2: Run rlsentry on a project's migrations (attacking: changes the spec's scenario)

Given a Supabase project's folder whose migrations create three tables, two whose reads an
anonymous visitor gets rows from and one whose read returns nothing,
when the user runs rlsentry on the folder,
then it prints the two exposed verdicts with their basis and evidence, stops on the third naming
the table and saying protected verdicts come with `anon-read-protected`, destroys the copy, and
exits `2`; on a folder with only the two, it exits `1`.

### S-3: Read the text summary (reports: changes the spec's scenario)

Given a run on a project with one exposed read,
when it finishes,
then the summary shows one line per table and operation (the table with its schema, the verdict and
the basis), the exposed table's evidence row, and the exit code with what it means.

### S-4: A table outside `public` in an exposed schema is attacked (attacking: changes the spec's scenario)

Given a project whose Supabase configuration exposes a second schema, and a table in it with
row-level security off on which the migrations grant the schema's use and reads to `anon`,
when the user runs rlsentry,
then that table's read is exposed and the report names it with its schema; without those grants,
the run stops naming the schema, since Supabase grants nothing outside `public` by default (#22).

### S-5: The copy is built, seeded, kept apart and destroyed (throwaway copy, live targets: new)

Built as in the spec: *The copy is gone when a run ends*, *A copy left by a killed run is removed by
the next*, *A migration cannot reach the machine*, *A setting a migration makes for the REST layer
stops the run*, *A setting a migration puts on the anonymous role stops the run*, *Migrations
written for Supabase build*, *Every table is seeded with the values its rules name*, *Two runs at
once do not meet* (throwaway copy); *A live target is refused* (live targets). *A table created
without grants is read as on Supabase* is built for its first half (exposed); its revoked-grant
half is `anon-read-protected`'s.

### S-6: Tables that reference Supabase's users are seeded (throwaway copy: new, #22)

Given a table whose key references Supabase's users table, as most Supabase projects' profile
tables do,
when the user runs rlsentry,
then the users table holds fake users before the attack, every row of the table points at one of
them, and the table gets a verdict or a stop the verdicts area names, never a stop for an unseeded
parent.

### S-7: A PostgreSQL or PostgREST of another release series stops the run (throwaway copy: changes the spec's scenario and rule)

Given a machine whose PostgreSQL is not 16 at 16.15 or later, or whose PostgREST is not 12.2 at
12.2.12 or later,
when the user runs rlsentry,
then nothing is built, the message names the program, the version found and the series needed, and
the command exits `2`; within the series, the run goes ahead and both reports name the exact
versions the copy ran. The versions are read from each program's `--version` and confirmed from
the running server. A test shows the stop by putting first on the path a program that only reports
another version; this is the one stand-in S-10 allows.

### S-8: The lab, for reads that are exposed (lab: changes the spec's scenarios)

Given rlsentry installed,
when the user lists the lab, and runs each lab schema by name,
then the list names each schema with its flaw in one line, and each schema's verdicts, exit code
and any stop are exactly those its statement gives; between them the schemas show a read exposed
for each reason the verdicts area gives (row-level security off, a policy admitting everyone, a
policy admitting some rows, a grant on some columns, a request without a key).

### S-9: What this task leaves marked for `anon-read-protected` (spec: changes markers)

Given the merged spec,
when someone reads the areas,
then every scenario this task built is under Scenarios, and each `anon-read` scenario it did not
build is under Not yet built marked `anon-read-protected`: *A policy that compares the key's project
reference stops the run* (attacking); *The lab shows every answer a read can get* (lab); *The basis
of a protected read says where the promise ends* (reports); *Read a table whose policies admit no
anonymous visitor*, *Read a table the anonymous visitor holds no grant on*, *An empty answer the
database does not explain stops the run*, *A refusal that only imitates the database stops the
run*, *A read policy that depends on a request header stops the run*, *A column filled with the time
does not stop the run* (verdicts); and the revoked-grant half of *A table created without grants is
read as on Supabase* (throwaway copy). No scenario is marked `anon-read` any more.

### S-10: Every behaviour is shown on the real database and REST layer (new; corrects the pitfall "a claim … written without running it", count 2)

Given the test suite,
when it runs on a machine with PostgreSQL and PostgREST of the accepted series,
then every scenario of S-1 to S-8 is shown by a test that builds a real copy and sends real
requests, with no stand-in for PostgreSQL or PostgREST except S-7's version stand-in; on a machine without them, the suite fails naming what is
missing instead of skipping. `test_command` in `.shilaycow/config.yml` runs it.

### S-11: A term is defined in one place (new; corrects the pitfall "a fact stated in two places", count 2)

Given the repository,
when the test suite runs,
then a check fails if a term defined under Terms in `docs/spec/index.md` (a line `- **term**: ...`)
is defined the same way in another file of `docs/spec/`, naming the term and the file, and passes
on the spec as merged; and the sentence in `docs/tasks/v3-spec/checks.md` "On the task branch it
prints `first open task: v3-spec` and `anon-read depends on: v3-spec`" (#20) is replaced by one
that describes what the check prints without stating its current output.

## How to try it

1. On a machine (or cloud session) with PostgreSQL 16 and PostgREST 12.2 installed, check out
   `task/anon-read-copy`, install rlsentry as its README says, and run the test command from
   `.shilaycow/config.yml`: every test passes.
2. `rlsentry lab` lists the lab; run one schema by name and read the summary and exit code.
3. Write a folder with one migration creating a table with row-level security off, run rlsentry on
   it with a JSON report asked for, and read both forms: exposed, the evidence row, exit `1`.
4. Add a migration with an open read policy and one with no policy: the run reports the first,
   stops on the second, exit `2`.
5. While a run attacks, press Ctrl-C, then check that no `postgres` or `postgrest` process of it is
   left.
6. Run with `--target https://example.supabase.co`: refused, exit `2`, nothing built.

## Critical areas

- The safety boundary: the copy is destroyed however a run ends, migration code cannot reach the
  machine, nothing is sent anywhere but the copy, and `--target` is refused.
- The exposed verdict and its evidence: an exposed read must rest on rows the copy really holds.

## Assumptions

- **Installing PostgREST**: the cloud environment's setup script downloads PostgREST 12.2.12 from
  its GitHub release and puts it on the path; the owner adds those lines. Until a session starts with it installed, no scenario can be shown, and
  the run opens a `needs-owner` issue rather than build blind.
- **Versions**: PostgreSQL 16 from 16.15 and PostgREST 12.2 from 12.2.12, as S-7 says; this replaces
  the spec's exact pins of 16.16 and 12.2.12, which this environment cannot meet (PostgreSQL 16.15
  is what its packages give). The reports name the exact versions.
- **Language and install**: Python 3.10 or later, installed with `pip` from the repository; the
  builder chooses the layout and records it in the trail.
- **Inputs the spec leaves open (#23)**: a folder with no `.sql` file stops with exit `2` saying so;
  migrations that create no table in an exposed schema give an empty report and exit `0`; a table
  with no columns gets a stop naming it; a partitioned table is attacked through its parent only,
  and its partitions are listed as reached through it; migration files are ordered by name, and two
  names that differ only in case stop the run; a folder with `supabase/migrations/` uses only that
  subfolder and says so; a table on which `anon` may read no column gets no read attempt and is
  passed to `anon-read-protected`'s stop; any setting a migration puts on the roles `anon`,
  `authenticated` or `authenticator`, and any `pgrst.*` setting anywhere, stops the run naming the
  role and setting, since those roles are the only ones PostgREST and the visitor pass through;
  other settings on the role `postgres` (such as `search_path`) do not stop it; no limit on table count or row size, but each request has a
  30-second timeout, a timeout stops the run naming the table.
- **Requests without a key**: rlsentry sends every read both with the anon key and without a key,
  as the spec says; that hosted Supabase lets a keyless request through is from its documentation,
  not a run (#23), and the reports' basis says when a verdict rests on the keyless request.
- **Size**: one pull request; if the builder finds it too large, the plan cuts it into tickets.
