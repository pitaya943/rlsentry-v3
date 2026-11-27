# v3-spec: the specification and roadmap of rlsentry v3

## Goal

The owner, and every builder after this task, can read in `docs/spec/` what rlsentry v3 is for,
who it defends against, and how it behaves, area by area, as Given / When / Then scenarios they can
check a build against; and `docs/roadmap.json` says which task builds which part, in an order that
puts what is hardest to change later first. Nothing is built in this task: it is documents only.

rlsentry v3 is a research and teaching tool, run professionally, about Supabase projects whose
tables an anonymous visitor holding only the public anon key can read or change (the class of flaw
behind CVE-2025-48757). It is a rebuild of the idea behind `pitaya943/rlsentry-v2`, designed again
from what users need, not from v2's documents.

### What users need (the demands the spec is designed from)

These are the demands, in the owner's terms. The spec turns each into scenarios and rules of its own.

1. **See what an anonymous visitor really gets.** For each table of a project and each of read,
   insert, update and delete, a user learns whether an anonymous visitor could really do it,
   shown by a real attempt, with the row involved as evidence.
2. **Never be told "safe" by mistake.** A "protected" answer rests on the database's own account of
   the refused attempt, never on a status code or an empty answer. When the tool cannot tell, it
   says so and stops instead of guessing.
3. **Never harm what is not yours.** By default the tool attacks only a throwaway copy it builds
   itself from a project's migrations, on this machine, and destroys it however the run ends.
   Nothing in a migration can reach the machine running the tool.
4. **Learn from bundled examples.** A lab of deliberately flawed schemas, each named for its
   mistake, shows every kind of answer without a project of one's own.
5. **Read the result as a person and as a script.** A text summary, a JSON report with a published
   schema, an exit code a script can act on, and one self-contained HTML report per run that opens
   offline and can be published as a Claude Artifact unchanged.
6. **Cover the whole target over time.** Beyond the anonymous visitor on tables: a logged-in user
   against another user's rows; views, storage buckets and database functions callable over the API;
   a real app built the way an inexperienced user would build it, studied as research; probing of a
   live project the user owns, non-destructively and only when the user opts in and proves
   ownership; a check that runs on a pull request's migrations; and a survey of related work.

## Out of scope

- Any code, test or workflow. This task writes documents only (`docs/spec/`, `docs/roadmap.json`,
  this task's folder).
- Copying v2: no passage of `rlsentry-v2/docs/` is copied into v3's spec. v2 may be read as prior
  art; each v3 rule says its own reason.
- Writing the scenarios of roadmap tasks after the next one in full: those tasks' briefs write
  them. This task writes in full only the scenarios of the next task (`anon-read`), and for every
  later task a one-line goal in the roadmap.
- The survey of related work itself (its own roadmap task, `related-work`).
- Deciding live-probe's exact technique: its area states only the boundary (ownership proof,
  opt-in, no write to real data, no real values in any report); its own brief decides the rest.

## Scenarios

The spec's areas are new; every scenario below is new.

### S-1: A reader learns what v3 is and what it will never do

Given the merged spec,
when someone opens `docs/spec/index.md`,
then it says in two or three sentences what rlsentry v3 is, lists each area with a one-line link,
defines once every term the areas' scenarios use (at least: anonymous visitor, the copy, operation,
the two verdicts, basis, evidence, lab, exit codes), and lists what rlsentry deliberately does not
do.

### S-2: A reader finds who rlsentry defends against

Given the merged spec,
when someone opens its threat model,
then it says what the attacker holds (the project URL and the anon key, or later a logged-in
user's session), what they can send, what counts as a successful attack for each operation, what
the tool itself must never be able to do (reach anything but its own copy by default; let
migration code reach the host; report a live project's real values), and which of these each
area's rules enforce.

### S-3: Every demand has scenarios or a roadmap task

Given the six demands above,
when someone checks the spec and the roadmap against them,
then each of demands 1 to 5 is covered by at least one scenario in an area (under Scenarios or
Not yet built), and each part of demand 6 is the goal of a task in `docs/roadmap.json`. A table in
the task's folder (`docs/tasks/v3-spec/coverage.md`) maps each demand to those scenarios or tasks.

### S-4: The next task can start from the spec alone

Given the merged spec,
when the next task (`anon-read`) agrees its brief,
then every scenario it is meant to build is already under Not yet built in an area, marked
`anon-read`, written as Given / When / Then in the user's words with no class, table or file
names of rlsentry's own code, and each one names how a person or a test would show it.

### S-5: The roadmap orders the work and passes the harness's check

Given the merged `docs/roadmap.json`,
when `state.py` from the shilaycow harness reads it,
then it reports no problem, names `anon-read` as the next task, and the order has every task after
its dependencies, the verdict and report model before the HTML report, and the copy and its safety
before anything that attacks a live project. Each task's goal says what a user can try once it is
merged.

### S-6: The spec is v3's own

Given v3's spec and v2's `docs/spec/`,
when someone compares them,
then no run of 12 or more consecutive words in a v3 spec file appears in a v2 spec file (a check
script in the task's folder shows the comparison), and where v3 decides a rule the same way v2
did, the rule gives v3's reason.

## How to try it

1. Read `docs/spec/index.md`, then each area it links; check S-1, S-2 and S-4 by eye.
2. Read `docs/tasks/v3-spec/coverage.md` and follow each row to its scenario or roadmap task (S-3).
3. From the repository root: `python3 ~/.claude/skills/shilaycow/state.py` and check that
   `problems` is empty and `next_task` is `anon-read` once the roadmap is on `main` (S-5); on the
   task branch, read the roadmap's order against S-5.
4. Run the overlap check in `docs/tasks/v3-spec/` against a clone of `pitaya943/rlsentry-v2` and see
   it report no shared run of 12 words (S-6).

## Critical areas

- The threat model and the safety boundary: what the tool may reach and what it never may, above
  all the rules for live targets.
- The verdict model: what makes an answer "exposed" or "protected", since every later task and
  every report rests on it.

## Assumptions

- **Stack**: Python 3.10+ command-line tool; the copy is PostgreSQL 16 with PostgREST, versions
  pinned in the spec, on a local-process backend and a Docker backend. The spec names behaviour,
  not modules.
- **Areas**, as users would name them: attacking a project, verdicts and evidence, reports (text,
  JSON, HTML), the throwaway copy, the lab, live targets, and the threat model. The builder may
  merge or split them if a scenario fits none, and says so in the trail.
- **HTML report**: one file, all styles and scripts inline, no network request when opened, so it
  works offline and as a published Claude Artifact; it shows the same facts as the JSON report,
  never more. It holds only fake rows from the copy.
- **Live targets**: allowed only in the late `live-probe` task, only against a project whose owner
  proves ownership the way that task's brief decides, opt-in per run, with no write to real data
  and no real row value in any report. Until then `--target` is refused.
- **Roadmap** (order proposed; the builder may refine and says why in the trail):
  `v3-spec` → `anon-read` (copy on local processes, seeding, READ verdicts, text and JSON report,
  part of the lab, refused live target) → `anon-write` (insert, update, delete, value search, full
  lab) → `html-report` → `docker-backend` → `related-work` → `authenticated-attack` →
  `more-surfaces` (views, storage, functions) → `real-app-study` (the owner builds the app by hand)
  → `ci-gate` → `live-probe`.
- **Size of each later task**: one pull request a person can review closely; a task that turns out
  larger is split by its own brief, not by this one.
- **Language**: the spec and the roadmap are in English.
