# rlsentry v3

rlsentry v3 is a command-line tool for research and teaching that answers one question about a
Supabase project: what could someone who knows only the project's URL and its public anon key
really read, create, change or delete? It answers by building a disposable database from the
project's migrations on this machine, attacking it over the same REST layer Supabase exposes, and
showing for every table and operation the attempt and the fake row that proves what got through.
It never touches a real project's data.

What follows is what the system is meant to be, area by area. Scenarios that hold now are under
each area's Scenarios; those agreed but not built yet are under Not yet built, each marked with the
task that builds it. The order of those tasks is in [the roadmap](../roadmap.json).

## Areas

- [Threat model](threat-model.md): who rlsentry plays, what they may send, what counts as a win
  for them, and what the tool itself must never be able to do.
- [Verdicts and evidence](verdicts.md): when an operation is exposed or protected, which signal
  from the database each answer rests on, when a run stops instead, and the exit codes.
- [Attacking a project](attacking.md): pointing rlsentry at a folder of migrations or a lab
  schema, and what one run does from start to end.
- [The throwaway copy](throwaway-copy.md): the database a run builds, fills with fake rows and
  destroys, where it runs, and how it is kept away from the host.
- [Reports](reports.md): the text summary, the JSON report and its schema, and the HTML report.
- [The lab](lab.md): the bundled schemas, each flawed on purpose and named for its flaw.
- [Live targets](live-targets.md): the boundary around ever pointing rlsentry at a real project.

## Terms

- **anonymous visitor**: whoever holds the project's URL and its public anon key and nothing else.
  In the copy, every request this visitor sends runs as the database role `anon`.
- **anon key**: the key Supabase publishes in every client app; it is not a secret, so anyone who
  loads the app has it.
- **logged-in user**: a visitor who also holds a session the project's own sign-up issued them.
  Attacked only from the `authenticated-attack` task onward.
- **the copy**: the disposable PostgreSQL database with PostgREST in front of it that one run builds
  on this machine from a project's migrations, attacks, and destroys however the run ends.
- **backend**: where the copy runs: as local processes, or in Docker containers.
- **seeding**: filling every table of the copy with fake rows, made up by rlsentry, before the
  attack begins.
- **the direct view**: rlsentry's own connection to the copy's database, as a role row-level
  security does not apply to. It is how rlsentry learns what a table really holds before and after
  an attempt. The anonymous visitor never has it.
- **operation**: one of read, insert, update and delete. Each is attacked on its own, on every
  table.
- **attempt**: the one request rlsentry sends as the anonymous visitor to try an operation on a
  table (after an insert or update refused by row-level security, each try of the value search is an
  attempt too).
- **row-level security**: PostgreSQL's per-row access rules on a table; **policy**: one such rule.
  **grant**: a privilege a role holds or lacks on a whole table or on some of its columns, checked
  before any policy.
- **verdict**: the answer for one table and one operation. There are exactly two:
  - **exposed**: the attempt really did what the visitor wanted, as the direct view confirms;
  - **protected**: the attempt was refused or kept from every row, as the database's own record of
    that attempt confirms.
- **basis**: the one line that says why a verdict was given.
- **evidence**: for an exposed verdict, the fake row that was read, created, changed (before and
  after) or deleted, as the direct view holds it.
- **the database's own account**: what PostgreSQL itself records about an attempt (its server log
  of that statement, with the error code and the place in PostgreSQL's own code that raised it) and
  what its catalog says about the table. It is defined in [Verdicts and evidence](verdicts.md).
- **value search**: once an insert or an update has been refused by row-level security, the further
  attempts rlsentry makes with new rows (insert) or new values (update) built from the table's own
  column defaults, checks and policies, looking for one the policies let in.
- **the lab**: the bundled schemas, each with a deliberate flaw and named for it.
- **`--target`**: the command-line option naming a live project. It is refused until the
  `live-probe` task.
- **exit codes**: `0` nothing was exposed; `1` at least one operation was exposed; `2` the run could
  not build the copy, attack it, or finish. See [Verdicts and evidence](verdicts.md).

## What rlsentry deliberately does not do

- It does not attack a real project. Until `live-probe`, `--target` is refused; after it, only a
  project whose owner proves ownership and opts in for that run, with no write to its data and no
  real value in any report.
- It does not judge intent. A table meant to be public reads as exposed: the tool says what the
  visitor can do, and the person decides whether that was meant.
- It does not give a third answer. No "probably", no "unknown" in a report: when it cannot show
  either verdict, the run stops.
- It does not fix anything: it suggests no policy and edits no migration.
- It does not promise more than it tried. Protected means the attempts it made, against the rows
  the copy held, were refused; it is not a proof that no request could ever succeed.
- It sends nothing anywhere but the copy it built: no telemetry, no lookup, no upload.
- It does not test the rest of Supabase (sign-in, Edge Functions, Realtime, GraphQL, the dashboard),
  nor look for flaws that are not about who may read or change what (injection, denial of
  service, leaked secrets).
- Until the roadmap reaches them, it attacks neither as a logged-in user nor anything but tables:
  views, storage buckets and database functions come with `authenticated-attack` and
  `more-surfaces`.

## Changed by

- `v3-spec`: the first version of this index.
