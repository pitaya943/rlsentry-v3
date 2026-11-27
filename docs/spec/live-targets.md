# Live targets

This area states the boundary around ever pointing rlsentry at a real Supabase project instead of
its own copy.

## Scenarios

None hold yet: nothing is built. The scenario `anon-read` builds is under
[Not yet built](#not-yet-built).

## Rules

Every rule here was decided by `v3-spec`. Only the boundary is decided here; `live-probe`'s brief
decides how it is kept.

- **Until `live-probe`, `--target` is refused** before any connection is made, name lookup included,
  and the command exits `2`. Why: no rule written ahead of that task can be checked, and a refusal
  that came after a connection would already have reached the project.
- **From `live-probe` on, a live project is attacked only when all of these hold:**
  - the user proves they own the project, in the way `live-probe`'s brief decides;
  - the user opts in for that run, every run;
  - nothing rlsentry sends writes to the project's real data;
  - no report, log or message holds a value read from the project.

  Why: a live project holds other people's data. Ownership keeps rlsentry from being a tool against
  someone else's project; opting in per run keeps a saved command from attacking without the user
  choosing to; no write keeps a probe from causing the harm it measures; and no real value keeps a
  report safe to share ([threat model](threat-model.md#what-rlsentry-itself-must-never-do), rule 4).

## Not yet built

"Shown by" says how a person or a test sees the scenario hold. Probing a live project is
`live-probe`'s: a user who proves they own a live Supabase project, and opts in for the run, learns
what an anonymous visitor could read or change there, without any write to real data and with no
real value in the report.

### A live target is refused (`anon-read`)

Given a project URL and a key,
when the user runs rlsentry with `--target` naming that URL,
then nothing is built and no request or name lookup is made, the message says live targets are not
available yet, and the command exits `2`.
Shown by: a test points `--target` at an address it watches and checks that nothing arrives there,
the message and the exit code.

## Changed by

- `v3-spec`: the first version of this area.
