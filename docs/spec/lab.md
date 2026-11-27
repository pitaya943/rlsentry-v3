# The lab

This area says what the bundled schemas are: projects flawed on purpose, each named for its flaw, so
that a user can see every kind of answer rlsentry gives without a project of their own.

## Scenarios

"Shown by" names the test that shows a scenario hold; every test builds a real copy and sends real
requests.

### List the lab

Given rlsentry installed,
when the user lists the lab with `rlsentry lab`,
then each schema is shown with its name and its flaw in one line, and nothing is built.
Shown by: `tests/test_lab.py::test_the_list_names_each_schema_with_its_flaw_and_builds_nothing`.

### Run a lab schema

Given a lab schema rlsentry ships,
when the user runs it by name with `rlsentry lab <name>`,
then its verdicts, exit code and any stop are exactly those its statement gives.
Shown by: `tests/test_lab.py::test_each_lab_schema_gives_what_its_statement_says`, which runs every
lab schema by name and compares each result with its statement.

### The lab shows a read exposed for every reason

Given the lab as rlsentry ships it,
when the user runs each schema in it,
then between them they show a read exposed for each reason the verdicts area gives: row-level
security off, a policy admitting everyone, a policy admitting some rows, a grant on some columns,
and a request without a key.
Shown by: `tests/test_lab.py::test_between_them_the_schemas_show_a_read_exposed_for_each_reason`.

## Rules

Every rule here was decided by `v3-spec`, except where a rule names `anon-read-copy`.

- Each lab schema is a folder of migrations written as a Supabase project would write them, and runs
  exactly as a user's folder does. Why: a lab that took another path through rlsentry would teach
  something the tool does not do on a real project.
- Each is named for its flaw in the user's words, not for the answer it gives. Why: the learner meets
  the mistake first and the verdict second, which is how they would meet it in their own project.
- Each states, in a file beside its migrations, its flaw in one or two sentences and the answer it is
  meant to give for each table and operation: exposed, protected, or that the run stops, and why.
  Why: a learner can check the run against what they were told to expect, and the statement is what
  rlsentry's own tests check every lab schema against, so the lab cannot drift from the tool.
- The lab holds, between its schemas, at least one table for every kind of answer the tasks built so
  far give. `anon-read-copy` brings the schemas whose flaw shows as an exposed read, and one that
  stops (a migration that fails); `anon-read-protected` adds schemas whose statement expects a
  protected read; `anon-write` completes it with every verdict kind for writes. Why: demand 4 is to see every kind of answer, and an answer the lab never gives is one
  a learner first meets on a real project.
- Lab schemas hold no real data and no real project's schema. Why: they are published with the tool.
- `rlsentry lab` lists the lab; `rlsentry lab <name> [--json FILE]` runs one schema
  (`anon-read-copy`). A user's own folder named `lab` is run as `rlsentry ./lab`. Why: a lab name
  and a folder path would otherwise share the one argument.

## Not yet built

Each scenario below is built by the task it is marked with. "Shown by" says how a person or a test
sees it hold.

### The lab shows every answer a read can get (`anon-read-protected`)

Given the lab as `anon-read-protected` ships it,
when the user runs each schema in it,
then between them they show a read exposed for each reason the verdicts area gives (row-level
security off, a policy admitting everyone, a policy admitting some rows, a grant on some columns, a
request without a key), a read protected by row-level security and one by a missing grant, and a run
that stops because a policy reads a request header.
Shown by: a test collects the answers of every lab schema and checks each listed kind appears.

## Changed by

- `v3-spec`: the first version of this area.
- `anon-read-copy`: the first lab schemas, `rlsentry lab`, and the scenarios it built moved up to
  Scenarios.
