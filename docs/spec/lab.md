# The lab

This area says what the bundled schemas are: projects flawed on purpose, each named for its flaw, so
that a user can see every kind of answer rlsentry gives without a project of their own.

## Scenarios

None hold yet: nothing is built. The scenarios `anon-read` builds are under
[Not yet built](#not-yet-built).

## Rules

Every rule here was decided by `v3-spec`.

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
  far give. `anon-read` brings the part of the lab whose flaws show on a read, and at least one
  schema that is protected and one that stops; `anon-write` completes it with every verdict kind
  for writes. Why: demand 4 is to see every kind of answer, and an answer the lab never gives is one
  a learner first meets on a real project.
- Lab schemas hold no real data and no real project's schema. Why: they are published with the tool.

## Not yet built

Each scenario below is built by the task it is marked with. "Shown by" says how a person or a test
sees it hold.

### List the lab (`anon-read`)

Given rlsentry installed,
when the user asks for the list of lab schemas,
then each is shown with its name and its flaw in one line, and nothing is built.
Shown by: a test checks the list names every bundled schema with its flaw; a person reads it and
picks one.

### Run a lab schema (`anon-read`)

Given a lab schema whose flaw shows on a read,
when the user runs rlsentry on it by name,
then the verdicts, the exit code and any stop are exactly those its statement gives.
Shown by: a test runs every lab schema and compares each result with its statement.

### The lab shows every answer a read can get (`anon-read`)

Given the lab as `anon-read` ships it,
when the user runs each schema in it,
then between them they show a read exposed for each reason the verdicts area gives (row-level
security off, a policy admitting everyone, a policy admitting some rows, a grant on some columns, a
request without a key), a read protected by row-level security and one by a missing grant, and a run
that stops because a policy reads a request header.
Shown by: a test collects the answers of every lab schema and checks each listed kind appears.

## Changed by

- `v3-spec`: the first version of this area.
